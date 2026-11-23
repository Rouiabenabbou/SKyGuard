"""
Login and user management (v1.1).

POST   /api/auth/login              {"username","password"} -> token + role
POST   /api/auth/logout             end this token
GET    /api/auth/me                 who am I
GET    /api/auth/config             is login switched on (public)
POST   /api/auth/password           change my own password
GET    /api/auth/users              list users                    (admin)
POST   /api/auth/users              create a user                 (admin)
PUT    /api/auth/users/{name}       change role / active / password (admin)
DELETE /api/auth/users/{name}       delete a user                 (admin)
GET    /api/audit                   security audit log            (admin)
GET    /api/audit/export.csv        audit log as CSV              (admin)
v2.1:
GET    /api/audit/verify            check the audit hash chain    (admin)
GET    /api/auth/roles              roles, labels and permissions
POST   /api/auth/mfa/setup          start two-factor setup (returns the key once)
POST   /api/auth/mfa/enable         {"code"} switch two-factor on
POST   /api/auth/mfa/disable        {"code"} switch it off
DELETE /api/auth/users/{name}/mfa   an admin resets a user's two-factor (lost phone)
"""
import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, config, mfa, soc_access, tenancy
from app.database import get_db
from app.models import AuditLog, AuthSession, Company, CompanyMember, User, UserMfa, utcnow

router = APIRouter(prefix="/api", tags=["auth"])

Role = Literal["viewer", "soc_l1", "soc_l2", "soc_l3", "soc_manager", "operator", "admin"]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=12)  # v2.1: two-factor code


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(max_length=200)


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(max_length=200)
    role: Role = "viewer"
    company_id: str | None = Field(default=None, max_length=40)  # v1.2: None = platform user


class UserUpdate(BaseModel):
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


def current_user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


# ---------------------------------------------------------- v1.2 companies
def members_of(db: Session, company_id: str) -> set[str]:
    return {m.username for m in db.query(CompanyMember).filter(CompanyMember.company_id == company_id)}


def user_dict(db: Session, user: User) -> dict:
    cid = tenancy.company_id_of_user(db, user.username)
    company = db.get(Company, cid) if cid else None
    return {**user.to_dict(), "company_id": cid, "company_name": company.name if company else None,
            "role_label": soc_access.ROLE_LABELS.get(user.role, user.role),
            "permissions": sorted(soc_access.permissions_of(user.role)),
            "mfa_enabled": auth.mfa_enabled(db, user.username),
            "mfa_required": user.role in config.MFA_REQUIRED_ROLES}


def _check_same_company(db: Session, username: str) -> None:
    """A company admin may only manage the users of their own company."""
    scope = tenancy.current()
    if scope.is_company and tenancy.company_id_of_user(db, username) != scope.company_id:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")


_default_cache: dict = {}


def default_passwords_in_use(db: Session) -> list[str]:
    """Accounts that still have their first-start password (cached until a user changes)."""
    if "users" not in _default_cache:
        defaults = [(u, pw, r) for u, pw, r in config.DEFAULT_USERS] + [
            (c[4], c[5], "admin") for c in config.DEMO_COMPANIES]  # v1.2 demo company admins
        from app.big_companies import BIG_COMPANY_ADMINS
        defaults += [(u, pw, "admin") for u, pw in BIG_COMPANY_ADMINS]  # v1.4
        _default_cache["users"] = [u for u, pw, _ in defaults
                                   if (user := db.get(User, u)) is not None and user.active
                                   and auth.verify_password(pw, user.password_hash)]
    return _default_cache["users"]


@router.get("/auth/config")
def auth_config(db: Session = Depends(get_db)):
    """Public: is login on, and are the first-start passwords still in use (shown as a warning)."""
    return {"auth_enabled": config.AUTH_ENABLED,
            "default_passwords": bool(config.AUTH_ENABLED and default_passwords_in_use(db))}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else ""
    name = body.username.strip()
    locked = auth.is_locked(name)
    if locked:
        auth.audit(db, username=name, role="-", method="POST", path="/api/auth/login", status=429,
                   outcome="denied", ip=ip, action="login blocked (too many wrong passwords)")
        raise HTTPException(status_code=429, detail=f"Too many wrong passwords. Try again in {int(locked) + 1} s.")
    user = db.get(User, name)
    if user is None or not user.active or not auth.verify_password(body.password, user.password_hash):
        auth.record_failure(name)
        auth.audit(db, username=name, role=user.role if user else "-", method="POST", path="/api/auth/login",
                   status=401, outcome="failed", ip=ip, action="login failed")
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    if auth.mfa_enabled(db, user.username):  # v2.1: second factor
        if not body.code:
            return {"mfa_required": True, "token": None}
        m = db.get(UserMfa, user.username)
        step = mfa.verify(m.secret, body.code, m.last_step)
        if step is None:
            auth.record_failure(name)
            auth.audit(db, username=name, role=user.role, method="POST", path="/api/auth/login",
                       status=401, outcome="failed", ip=ip, action="login failed (wrong two-factor code)")
            raise HTTPException(status_code=401, detail="Wrong or already used two-factor code.")
        m.last_step = step
        db.commit()
    auth.clear_failures(name)
    token = auth.create_session(db, user)
    auth.audit(db, username=user.username, role=user.role, method="POST", path="/api/auth/login",
               status=200, ip=ip, action="login")
    return {"token": token, "user": user_dict(db, user), "expires_in_hours": config.AUTH_TOKEN_HOURS}


@router.post("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = auth.token_from(request)
    if token:
        auth.end_session(db, token)
    return {"logged_out": True}


@router.get("/auth/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    if user is None:  # login switched off
        return {"user": {"username": "guest", "role": "admin", "active": True, "company_id": None, "company_name": None,
                         "role_label": "Administrator", "permissions": sorted(soc_access.ALL), "mfa_enabled": False,
                         "mfa_required": False},
                "auth_enabled": config.AUTH_ENABLED}
    return {"user": user_dict(db, user), "auth_enabled": config.AUTH_ENABLED}


@router.post("/auth/password")
def change_password(body: PasswordIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=400, detail="Login is switched off, there is no account to change.")
    user = db.get(User, user.username)
    if not auth.verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="The current password is wrong.")
    problem = auth.password_problem(body.new_password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    user.password_hash = auth.hash_password(body.new_password)
    db.commit()
    _default_cache.clear()
    return {"changed": True}


@router.get("/auth/users")
def list_users(db: Session = Depends(get_db)):
    scope = tenancy.current()
    users = db.query(User).order_by(User.username).all()
    if scope.is_company:  # a company admin sees only their own colleagues
        mine = members_of(db, scope.company_id)
        users = [u for u in users if u.username in mine]
    return {"users": [user_dict(db, u) for u in users]}


@router.post("/auth/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db)):
    if db.get(User, body.username) is not None:
        raise HTTPException(status_code=409, detail=f"User '{body.username}' already exists.")
    problem = auth.password_problem(body.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    scope = tenancy.current()
    company_id = scope.company_id if scope.is_company else body.company_id
    if company_id and db.get(Company, company_id) is None:
        raise HTTPException(status_code=400, detail=f"Company '{company_id}' does not exist.")
    user = User(username=body.username, password_hash=auth.hash_password(body.password), role=body.role)
    db.add(user)
    if company_id:
        db.add(CompanyMember(username=body.username, company_id=company_id))
    db.commit()
    return {"created": True, "user": user_dict(db, user)}


def _admins_left(db: Session, excluding: str) -> int:
    """Other active PLATFORM admins. The platform must always keep one; a company
    can always be managed by the platform, so company admins are not counted."""
    if tenancy.company_id_of_user(db, excluding) is not None:
        return 1  # not a platform admin: no "last admin" rule
    admins = db.query(User).filter(User.role == "admin", User.active.is_(True), User.username != excluding).all()
    return sum(1 for u in admins if tenancy.company_id_of_user(db, u.username) is None)


@router.put("/auth/users/{username}")
def update_user(username: str, body: UserUpdate, db: Session = Depends(get_db)):
    _check_same_company(db, username)
    user = db.get(User, username)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    losing_admin = user.role == "admin" and ((body.role and body.role != "admin") or body.active is False)
    if losing_admin and _admins_left(db, username) == 0:
        raise HTTPException(status_code=409, detail="This is the last admin; create another admin first.")
    if body.password is not None:
        problem = auth.password_problem(body.password)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        user.password_hash = auth.hash_password(body.password)
    if body.role is not None:
        user.role = body.role
    if body.active is not None:
        user.active = body.active
    _default_cache.clear()
    if body.active is False or body.password is not None or body.role is not None:
        db.query(AuthSession).filter(AuthSession.username == username).delete()  # log them out
    db.commit()
    return {"updated": True, "user": user_dict(db, user)}


@router.delete("/auth/users/{username}")
def delete_user(username: str, request: Request, db: Session = Depends(get_db)):
    _check_same_company(db, username)
    user = db.get(User, username)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    me_ = current_user(request)
    if me_ is not None and me_.username == username:
        raise HTTPException(status_code=409, detail="You can't delete your own account.")
    if user.role == "admin" and _admins_left(db, username) == 0:
        raise HTTPException(status_code=409, detail="This is the last admin; create another admin first.")
    db.query(AuthSession).filter(AuthSession.username == username).delete()
    db.query(CompanyMember).filter(CompanyMember.username == username).delete()
    db.delete(user)
    db.commit()
    _default_cache.clear()
    return {"deleted": True, "username": username}


@router.get("/audit")
def audit_log(limit: int = Query(default=100, ge=1, le=2000), username: str | None = None,
              outcome: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    scope = tenancy.current()
    if scope.is_company:  # a company admin sees what their own users did
        q = q.filter(AuditLog.username.in_(members_of(db, scope.company_id)))
    if username:
        q = q.filter(AuditLog.username == username)
    if outcome:
        q = q.filter(AuditLog.outcome == outcome)
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    return {"count": len(rows), "entries": [r.to_dict() for r in rows]}


@router.get("/audit/export.csv")
def audit_csv(db: Session = Depends(get_db)):
    cols = ["id", "timestamp", "username", "role", "action", "method", "path", "status_code", "outcome", "ip"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    q = db.query(AuditLog)
    scope = tenancy.current()
    if scope.is_company:
        q = q.filter(AuditLog.username.in_(members_of(db, scope.company_id)))
    for r in q.order_by(AuditLog.id):
        d = r.to_dict()
        w.writerow([d[c] for c in cols])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="cybershield-audit-log.csv"'})


# ------------------------------------------------------------------ v2.1
@router.get("/auth/roles")
def roles():
    return {"roles": [{"id": r, "label": soc_access.ROLE_LABELS[r], "permissions": sorted(soc_access.permissions_of(r))}
                      for r in ("viewer", "soc_l1", "soc_l2", "soc_l3", "soc_manager", "operator", "admin")]}


def _me(request: Request, db: Session) -> User:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=400, detail="Login is switched off, there is no account.")
    return db.get(User, user.username)


@router.post("/auth/mfa/setup")
def mfa_setup(request: Request, db: Session = Depends(get_db)):
    """New secret (shown once). Two-factor is only on after /enable with a valid code."""
    user = _me(request, db)
    m = db.get(UserMfa, user.username)
    if m and m.enabled:
        raise HTTPException(status_code=409, detail="Two-factor login is already on. Switch it off first to get a new key.")
    secret = mfa.new_secret()
    if m is None:
        db.add(UserMfa(username=user.username, secret=secret, enabled=False))
    else:
        m.secret, m.last_step = secret, 0
    db.commit()
    return {"secret": secret, "otpauth_uri": mfa.otpauth_uri(secret, user.username), "digits": mfa.DIGITS, "period": mfa.STEP}


@router.post("/auth/mfa/enable")
def mfa_enable(body: CodeIn, request: Request, db: Session = Depends(get_db)):
    user = _me(request, db)
    m = db.get(UserMfa, user.username)
    if m is None:
        raise HTTPException(status_code=400, detail="Start the setup first.")
    step = mfa.verify(m.secret, body.code, m.last_step)
    if step is None:
        raise HTTPException(status_code=400, detail="Wrong code. Check the phone's clock and try the newest code.")
    m.enabled, m.last_step = True, step
    db.commit()
    return {"enabled": True}


@router.post("/auth/mfa/disable")
def mfa_disable(body: CodeIn, request: Request, db: Session = Depends(get_db)):
    user = _me(request, db)
    m = db.get(UserMfa, user.username)
    if m is None or not m.enabled:
        return {"enabled": False}
    if user.role in config.MFA_REQUIRED_ROLES:
        raise HTTPException(status_code=409, detail="Two-factor login is required for your role.")
    if mfa.verify(m.secret, body.code, m.last_step) is None:
        raise HTTPException(status_code=400, detail="Wrong code.")
    db.delete(m)
    db.commit()
    return {"enabled": False}


@router.delete("/auth/users/{username}/mfa")
def mfa_reset(username: str, db: Session = Depends(get_db)):
    _check_same_company(db, username)
    m = db.get(UserMfa, username)
    if m is not None:
        db.delete(m)
        db.commit()
    return {"reset": True, "username": username}


@router.get("/audit/verify")
def audit_verify(db: Session = Depends(get_db)):
    """Recompute the SHA-256 chain over the whole audit log (platform view)."""
    return {**auth.verify_chain(db), "checked_at": utcnow().isoformat() + "Z"}
