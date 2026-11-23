"""
Login, roles and the security audit log (v1.1).

* Passwords are stored as salted PBKDF2-SHA256 hashes (Python standard library).
* A login returns a random token. The browser sends it as
  "Authorization: Bearer <token>" (or ?token= for downloads and the WebSocket).
  Only the SHA-256 hash of the token is stored, so a copied database can't be
  used to log in.
* Too many wrong passwords lock that username for a short time.
* One middleware checks every request against the role rules below and writes
  every change (and every login) to the audit_log table.

Roles, from least to most rights:
  viewer    read everything, change nothing
  operator  respond to incidents: quarantine/release, resolve alerts, simulate
            attacks and failures, failover, exports, AI assistant
  admin     everything, including devices, the network builder, reset and users
v2.1 adds the SOC roles soc_l1 / soc_l2 / soc_l3 / soc_manager (operator level plus
permissions, see soc_access.py), TOTP two-factor login and a hash-chained audit log.
"""
import hashlib
import json
import hmac
import re
import secrets
import threading
import time
from datetime import timedelta

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app import config
from app.database import SessionLocal
from app.models import AuditChain, AuditLog, AuthSession, User, utcnow

ROLES = {"viewer": 1, "soc_l1": 2, "soc_l2": 2, "soc_l3": 2, "soc_manager": 2, "operator": 2, "admin": 3}
PBKDF2_ITERATIONS = 200_000

# Reachable without logging in.
PUBLIC = [("GET", r"/api/health"), ("POST", r"/api/iotda/push"), ("POST", r"/api/auth/login"), ("GET", r"/api/auth/config")]

# POST requests that only read or concern your own account: any logged-in user.
VIEWER_POSTS = [("POST", r"/api/auth/(logout|password)"), ("POST", r"/api/ai/(chat|report|explain-alert/\d+|investigate)"),
                ("PUT", r"/api/analytics/graph/layout"), ("POST", r"/api/auth/mfa/(setup|enable|disable)")]

# Changes only an admin may make. Every other change needs at least "operator";
# every read needs at least "viewer".
ADMIN_ONLY = [
    ("POST", r"/api/devices"),
    ("DELETE", r"/api/devices/[^/]+"),
    ("PUT", r"/api/devices/[^/]+/config"),
    ("PUT", r"/api/profiles/[^/]+"),
    ("POST", r"/api/network/(nodes|links)"),
    ("POST", r"/api/network/devices/[^/]+/access"),  # v1.5
    ("DELETE", r"/api/network/(nodes|links)/[^/]+"),
    ("POST", r"/api/simulation/reset"),
    ("POST", r"/api/quarantine/settings"),
    ("ANY", r"/api/auth/users.*"),
    ("GET", r"/api/audit.*"),
    ("ANY", r"/api/companies.*"),  # v1.2 (platform admins only, see tenancy.py)
    ("ANY", r"/api/notify/.*"),  # v1.2 phone alarm settings
    ("ANY", r"/api/ai/(settings|test)"),  # v1.4 AI key set from the dashboard
    ("POST", r"/api/devices/[^/]+/firmware"),  # v1.4
    ("POST", r"/api/analytics/history"),  # v1.3
    ("DELETE", r"/api/analytics/history"),
]

# Short names for the audit log (method, path regex, text).
ACTIONS = [
    ("POST", r"/api/auth/login", "login"),
    ("POST", r"/api/auth/logout", "logout"),
    ("POST", r"/api/auth/password", "change own password"),
    ("POST", r"/api/auth/users", "create user"),
    ("DELETE", r"/api/auth/users/[^/]+/mfa", "reset user two-factor"),
    ("DELETE", r"/api/auth/users/[^/]+", "delete user"),
    ("PUT", r"/api/auth/users/.+", "update user"),
    ("POST", r"/api/devices/[^/]+/quarantine", "quarantine device"),
    ("POST", r"/api/devices/[^/]+/release", "release device"),
    ("POST", r"/api/devices/[^/]+/command", "send device command"),
    ("POST", r"/api/devices/[^/]+/motion", "simulate movement"),
    ("PUT", r"/api/devices/[^/]+/config", "configure device"),
    ("PUT", r"/api/profiles/[^/]+", "set location / sensors"),
    ("POST", r"/api/devices", "add device"),
    ("DELETE", r"/api/devices/.+", "remove device"),
    ("POST", r"/api/network/nodes/[^/]+/state", "change node state"),
    ("POST", r"/api/network/links/[^/]+/state", "change link state"),
    ("POST", r"/api/network/devices/[^/]+/access", "re-wire device"),
    ("PUT", r"/api/soc/rules/[^/]+", "switch detection rule"),
    ("POST", r"/api/soc/rules/[^/]+/test", "test detection rule"),
    ("POST", r"/api/soc/alerts/\d+/action", "alert triage"),
    ("PUT", r"/api/analytics/graph/layout", "save network graph layout"),
    ("POST", r"/api/network/nodes", "add network node"),
    ("POST", r"/api/network/links", "add network link"),
    ("DELETE", r"/api/network/nodes/.+", "remove network node"),
    ("DELETE", r"/api/network/links/.+", "remove network link"),
    ("POST", r"/api/alerts/[^/]+/resolve", "resolve alert"),
    ("POST", r"/api/simulation/attack/.+", "simulate attack"),
    ("POST", r"/api/simulation/(start|pause|reset)", "simulation control"),
    ("POST", r"/api/quarantine/settings", "change auto-quarantine"),
    ("POST", r"/api/failover/settings", "change failover"),
    ("POST", r"/api/failover/drill.*", "failover drill"),
    ("POST", r"/api/ml/.+", "ML detector"),
    ("POST", r"/api/export/.+", "save export"),
    ("POST", r"/api/ai/(chat|report|explain-alert/.+)", "ask AI assistant"),
    ("POST", r"/api/companies", "create company"),
    ("PUT", r"/api/companies/devices/.+", "assign device to company"),
    ("PUT", r"/api/companies/.+", "update company"),
    ("DELETE", r"/api/companies/.+", "delete company"),
    ("PUT", r"/api/notify/settings", "change phone alarm"),
    ("POST", r"/api/notify/test", "send test alarm"),
    ("PUT", r"/api/ai/settings", "change AI key"),
    ("POST", r"/api/ai/test", "test AI key"),
    ("POST", r"/api/analytics/history", "generate history"),
    ("DELETE", r"/api/analytics/history", "delete history"),
    ("POST", r"/api/analytics/rollup", "summarise live data"),
    ("POST", r"/api/devices/[^/]+/maintenance", "maintenance mode"),
    ("POST", r"/api/devices/[^/]+/reboot", "reboot device"),
    ("POST", r"/api/devices/[^/]+/firmware", "firmware update"),
    ("POST", r"/api/incidents", "open incident"),
    ("POST", r"/api/incidents/\d+/phase", "incident phase change"),
    ("POST", r"/api/incidents/\d+/evidence", "add incident evidence"),
    ("PUT", r"/api/incidents/\d+/mitre", "incident MITRE mapping"),
    ("POST", r"/api/incidents/\d+/playbooks", "start playbook"),
    ("POST", r"/api/incidents/\d+/playbooks/\d+/steps/.+", "playbook step"),
    ("POST", r"/api/approvals", "request containment"),
    ("POST", r"/api/approvals/\d+/approve", "approve containment"),
    ("POST", r"/api/approvals/\d+/reject", "reject containment"),
    ("POST", r"/api/intel/iocs", "add IOC"),
    ("PUT", r"/api/intel/iocs/\d+", "update IOC"),
    ("DELETE", r"/api/intel/iocs/\d+", "delete IOC"),
    ("POST", r"/api/hunt/queries", "save hunting query"),
    ("DELETE", r"/api/hunt/queries/\d+", "delete hunting query"),
    ("POST", r"/api/ai/investigate", "AI analyst investigation"),
    ("POST", r"/api/soc/demo/start", "start demo scenario"),
    ("POST", r"/api/auth/mfa/setup", "start two-factor setup"),
    ("POST", r"/api/auth/mfa/enable", "enable two-factor login"),
    ("POST", r"/api/auth/mfa/disable", "disable two-factor login"),
    ("PUT", r"/api/incidents/.+", "update incident"),
    ("POST", r"/api/incidents/[^/]+/notes", "incident note"),
]


def _match(rules, method: str, path: str) -> bool:
    return any((m == "ANY" or m == method) and re.fullmatch(p, path) for m, p, *_ in rules)


def required_role(method: str, path: str) -> str | None:
    """The lowest role allowed to make this request (None = public)."""
    if not path.startswith("/api/") or _match(PUBLIC, method, path):
        return None
    if _match(ADMIN_ONLY, method, path):
        return "admin"
    if method in ("GET", "HEAD", "OPTIONS") or _match(VIEWER_POSTS, method, path):
        return "viewer"
    return "operator"


def action_name(method: str, path: str) -> str:
    for m, p, text in ACTIONS:
        if m == method and re.fullmatch(p, path):
            return text
    return f"{method} {path}"


# ------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(check, digest)
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    """None if the password is strong enough, else what is wrong."""
    if len(password) < 8:
        return "the password needs at least 8 characters"
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        return "the password needs letters and at least one number"
    return None


def seed_users(db: Session) -> None:
    """Create the default accounts on the first start (when there are no users)."""
    if db.query(User).count():
        return
    for username, password, role in config.DEFAULT_USERS:
        db.add(User(username=username, password_hash=hash_password(password), role=role))
    db.commit()


# ---------------------------------------------------------------- tokens
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_token_hash(token), username=user.username,
                       expires_at=utcnow() + timedelta(hours=config.AUTH_TOKEN_HOURS)))
    user.last_login = utcnow()
    db.query(AuthSession).filter(AuthSession.expires_at < utcnow()).delete()  # tidy old tokens
    db.commit()
    return token


def end_session(db: Session, token: str) -> None:
    db.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).delete()
    db.commit()


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    s = db.get(AuthSession, _token_hash(token))
    if s is None or s.expires_at < utcnow():
        return None
    user = db.get(User, s.username)
    return user if user is not None and user.active else None


def token_from(request_or_ws) -> str | None:
    header = request_or_ws.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request_or_ws.query_params.get("token")


# --------------------------------------------------- brute-force protection
_failures: dict[str, list[float]] = {}


def is_locked(username: str) -> float:
    """Seconds left on the lock for this username (0 = not locked)."""
    now = time.time()
    recent = [t for t in _failures.get(username, []) if now - t < config.LOGIN_LOCK_SECONDS]
    _failures[username] = recent
    if len(recent) >= config.LOGIN_MAX_FAILURES:
        return config.LOGIN_LOCK_SECONDS - (now - recent[0])
    return 0.0


def record_failure(username: str) -> None:
    _failures.setdefault(username, []).append(time.time())


def clear_failures(username: str) -> None:
    _failures.pop(username, None)


# -------------------------------------------------------------- audit log
_chain_lock = threading.Lock()
GENESIS = "0" * 64


def _row_hash(prev: str, r: AuditLog) -> str:
    """SHA-256 of the previous hash + every field of the row: changing or deleting a row breaks the chain."""
    text = "|".join([prev, str(r.id), r.timestamp.isoformat(timespec="microseconds") if r.timestamp else "", r.username,
                     r.role, r.action, r.method, r.path, str(r.status_code), r.outcome, r.ip])
    return hashlib.sha256(text.encode()).hexdigest()


def chain_pending(db: Session) -> int:
    """Add every audit row that is not chained yet to the hash chain (in id order)."""
    with _chain_lock:
        last = db.query(AuditChain).order_by(AuditChain.audit_id.desc()).first()
        prev, after = (last.hash, last.audit_id) if last else (GENESIS, 0)
        rows = db.query(AuditLog).filter(AuditLog.id > after).order_by(AuditLog.id).all()
        for r in rows:
            h = _row_hash(prev, r)
            db.add(AuditChain(audit_id=r.id, prev_hash=prev, hash=h))
            prev = h
        if rows:
            db.commit()
        return len(rows)


def verify_chain(db: Session) -> dict:
    """Recompute the chain. Reports the first row that was changed, deleted or added outside the chain."""
    links = {c.audit_id: c for c in db.query(AuditChain)}
    rows = db.query(AuditLog).order_by(AuditLog.id).all()
    prev = GENESIS
    checked = 0
    present = set()
    for r in rows:
        present.add(r.id)
        c = links.get(r.id)
        if c is None:
            return {"ok": False, "checked": checked, "total": len(rows), "broken_at": r.id,
                    "problem": f"audit row #{r.id} is not in the hash chain (written outside the application?)"}
        if c.prev_hash != prev:
            return {"ok": False, "checked": checked, "total": len(rows), "broken_at": r.id,
                    "problem": f"the row before #{r.id} was deleted or changed (previous hash does not match)"}
        if _row_hash(prev, r) != c.hash:
            return {"ok": False, "checked": checked, "total": len(rows), "broken_at": r.id,
                    "problem": f"audit row #{r.id} was modified after it was written"}
        prev = c.hash
        checked += 1
    missing = sorted(set(links) - present)
    if missing and missing[-1] > (max(present) if present else 0):
        return {"ok": False, "checked": checked, "total": len(rows), "broken_at": missing[-1],
                "problem": f"the newest audit row(s) from #{missing[0]} were deleted"}
    if missing:
        return {"ok": False, "checked": checked, "total": len(rows), "broken_at": missing[0],
                "problem": f"audit row #{missing[0]} was deleted"}
    return {"ok": True, "checked": checked, "total": len(rows), "last_hash": prev}


def audit(db: Session, *, username: str, role: str, method: str, path: str, status: int,
          outcome: str | None = None, ip: str = "", action: str | None = None) -> None:
    if outcome is None:
        outcome = "ok" if status < 400 else ("denied" if status in (401, 403) else "failed")
    db.add(AuditLog(username=username or "-", role=role or "-", action=action or action_name(method, path),
                    method=method, path=path[:200], status_code=status, outcome=outcome, ip=ip[:64]))
    db.commit()
    try:  # v2.1: tamper-evident hash chain
        chain_pending(db)
    except Exception as exc:
        db.rollback()
        print(f"[audit] hash chain skipped: {exc}")


# ------------------------------------------------------- v2.1 two-factor
def mfa_enabled(db: Session, username: str) -> bool:
    from app.models import UserMfa
    m = db.get(UserMfa, username)
    return bool(m and m.enabled)


def mfa_setup_needed(db: Session, user: User) -> bool:
    return user.role in config.MFA_REQUIRED_ROLES and not mfa_enabled(db, user.username)


# --------------------------------------------------------------- middleware
async def auth_middleware(request: Request, call_next):
    """Checks the role (and, v1.2, the company) for every /api request and audits every change."""
    from app import soc_access, tenancy

    method, path = request.method, request.url.path
    if method == "OPTIONS" or not path.startswith("/api/"):
        return await call_next(request)
    needed = required_role(method, path)
    ip = request.client.host if request.client else ""
    is_change = method not in ("GET", "HEAD")

    user = None
    scope = tenancy.PLATFORM
    if config.AUTH_ENABLED and needed is not None:
        with SessionLocal() as db:
            user = user_for_token(db, token_from(request))
            denied = None
            if user is None:
                denied = (401, "Please log in first (missing or expired token).")
            elif ROLES.get(user.role, 0) < ROLES[needed]:
                denied = (403, f"Your role '{user.role}' can't do this; it needs '{needed}'.")
            elif (perm := soc_access.required_permission(method, path, needed)) and not soc_access.has(user.role, perm):
                denied = (403, f"Your role '{user.role}' does not have the '{perm}' permission"
                               + (" (ask for containment in Approvals instead)." if perm == "contain" and soc_access.has(user.role, "contain_request") else "."))
            elif mfa_setup_needed(db, user) and not re.fullmatch(r"/api/auth/(me|mfa/.+|logout|config)", path):
                denied = (403, "Two-factor login is required for your role. Set it up first (Account menu, top right).")
            else:
                scope = tenancy.scope_for(db, user)
                problem = tenancy.request_problem(scope, method, path, dict(request.query_params))
                if problem:
                    denied = (403, problem)
            if denied:
                if is_change or needed == "admin" or denied[0] == 403:
                    audit(db, username=user.username if user else "-", role=user.role if user else "-",
                          method=method, path=path, status=denied[0], ip=ip)
                return JSONResponse({"detail": denied[1]}, status_code=denied[0])
    request.state.user = user
    request.state.scope = scope
    token = tenancy.set_current(scope)
    try:
        response = await call_next(request)
    finally:
        tenancy._current.reset(token)

    # v1.2: a company user never receives another company's devices in a JSON reply.
    if scope.is_company and scope.hidden and response.headers.get("content-type", "").startswith("application/json"):
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            clean = json.dumps(tenancy.scrub(json.loads(body), scope.hidden)).encode()
        except ValueError:
            clean = body
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        response = Response(content=clean, status_code=response.status_code, headers=headers,
                            media_type="application/json")

    # Logins are audited by the login route itself (it knows the username).
    if is_change and path not in ("/api/auth/login",):
        with SessionLocal() as db:
            audit(db, username=user.username if user else ("-" if config.AUTH_ENABLED else "auth-off"),
                  role=user.role if user else "-", method=method, path=path, status=response.status_code, ip=ip)
    return response
