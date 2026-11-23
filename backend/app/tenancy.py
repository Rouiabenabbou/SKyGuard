"""
Many companies on one system (v1.2, "multi-tenant").

The satellite, ground station, 5G tower, core and security server are SHARED
infrastructure (like a telecom provider). The IoT devices belong to companies
(a farm, an office building, a solar plant...).

* A user with a company ("company user") only sees and controls the devices of
  that company: their readings, alerts, events, quarantine records, routes,
  live WebSocket messages, CSV exports, report and AI answers.
* A user without a company is a PLATFORM user (the provider / SOC). A platform
  admin creates companies, their first admin, and decides which device belongs
  to which company. Platform users see everything.
* Shared infrastructure (start/pause/reset the simulation, failover, network
  failures and the network builder, auto-quarantine, ML) can only be changed by
  platform users, because it affects every company.

How it is enforced (backend, for every request):
1. auth_middleware works out the user's "scope" (see scope_for) and refuses a
   request that names a device of another company, or a platform-only action.
2. JSON replies and WebSocket messages are cleaned by scrub(): every item that
   belongs to another company's device is removed.
3. CSV exports, the report and the AI assistant read current_hidden() and leave
   those devices out.

Tables (new tables only, so older databases upgrade by themselves):
companies, company_members (username -> company), company_devices (device -> company).
"""
import contextvars
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import config

# ------------------------------------------------------------------ cache
# device_id -> company_id for every registered IoT device ("" = platform device).
_device_company: dict[str, str] = {}
_loaded = False


def refresh(db: Session | None = None) -> None:
    """Reload which device belongs to which company (call after any change)."""
    global _loaded
    from app.database import SessionLocal
    from app.models import CompanyDevice, Device

    own = db is None
    db = db or SessionLocal()
    try:
        owners = {r.device_id: r.company_id for r in db.query(CompanyDevice)}
        _device_company.clear()
        for (device_id,) in db.query(Device.device_id):
            _device_company[device_id] = owners.get(device_id, "")
        _loaded = True
    finally:
        if own:
            db.close()


def _ensure() -> None:
    if not _loaded:
        refresh()


def preassign(device_id: str, company_id: str) -> None:
    """Remember the owner of a device that is being created right now."""
    _ensure()
    _device_company[device_id] = company_id


def company_of_device(device_id: str) -> str:
    _ensure()
    return _device_company.get(device_id, "")


def devices_of(company_id: str) -> set[str]:
    _ensure()
    return {d for d, c in _device_company.items() if c == company_id}


def hidden_for(company_id: str | None) -> frozenset[str]:
    """Registered devices a member of this company must not see (empty for platform users)."""
    if not company_id:
        return frozenset()
    _ensure()
    return frozenset(d for d, c in _device_company.items() if c != company_id)


# ------------------------------------------------------------------ scope
@dataclass(frozen=True)
class Scope:
    company_id: str | None = None  # None = platform (sees everything)
    company_name: str = ""
    hidden: frozenset = field(default_factory=frozenset)

    @property
    def is_company(self) -> bool:
        return self.company_id is not None


PLATFORM = Scope()
_current: contextvars.ContextVar[Scope] = contextvars.ContextVar("tenant_scope", default=PLATFORM)


def company_id_of_user(db: Session, username: str) -> str | None:
    from app.models import CompanyMember
    m = db.get(CompanyMember, username)
    return m.company_id if m else None


def scope_for(db: Session, user) -> Scope:
    if user is None or not config.AUTH_ENABLED:
        return PLATFORM
    from app.models import Company
    cid = company_id_of_user(db, user.username)
    if cid is None:
        return PLATFORM
    company = db.get(Company, cid)
    return Scope(company_id=cid, company_name=company.name if company else cid, hidden=hidden_for(cid))


def set_current(scope: Scope):
    return _current.set(scope)


def current() -> Scope:
    return _current.get()


def current_hidden() -> frozenset[str]:
    return _current.get().hidden


# ------------------------------------------------------------------ scrub
ID_FIELDS = ("device_id", "node_id", "source_node", "target_node", "source", "target", "device", "id")
TEXT_FIELDS = ("description", "message", "reason", "title")


def _pattern(hidden: frozenset[str]):
    return re.compile(r"(?<![A-Z0-9-])(" + "|".join(re.escape(h) for h in sorted(hidden, key=len, reverse=True)) + r")(?![A-Z0-9-])")


def _mentions(item, hidden, pattern) -> bool:
    if isinstance(item, str):
        return item in hidden or bool(pattern.search(item))
    if isinstance(item, dict):
        if any(isinstance(item.get(f), str) and item.get(f) in hidden for f in ID_FIELDS):
            return True
        return any(isinstance(item.get(f), str) and pattern.search(item[f]) for f in TEXT_FIELDS)
    return False


def scrub(obj, hidden: frozenset[str]):
    """Remove everything about the hidden devices from a JSON-like object:
    list items that are (or name) such a device, and dict keys equal to its ID."""
    if not hidden:
        return obj
    pattern = _pattern(hidden)

    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items() if k not in hidden}
        if isinstance(o, list):
            return [walk(i) for i in o if not _mentions(i, hidden, pattern)]
        return o

    return walk(obj)


def message_is_hidden(data, hidden: frozenset[str]) -> bool:
    """A live message that is entirely about another company's device."""
    if not hidden or not isinstance(data, dict):
        return False
    pattern = _pattern(hidden)
    # e.g. {"device": {...}, "reading": {...}}: look one level down too
    return _mentions(data, hidden, pattern) or any(
        isinstance(v, dict) and _mentions(v, hidden, pattern) for v in data.values())


# ---------------------------------------------------- request-level checks
# Changes to shared infrastructure: platform users only.
PLATFORM_ONLY = [
    ("POST", r"/api/simulation/(start|pause|reset)"),
    ("POST", r"/api/network/(nodes|links)"),
    ("POST", r"/api/network/devices/[^/]+/access"),
    ("PUT", r"/api/soc/rules/[^/]+"),
    ("POST", r"/api/soc/rules/[^/]+/test"),
    ("POST", r"/api/soc/demo/start"),  # v2.1
    ("GET", r"/api/lab/report"),  # v2.2: covers every real board
    ("ANY", r"/api/iotda/status"),
    ("ANY", r"/api/ml/autoencoder(/reload)?"),
    ("DELETE", r"/api/network/(nodes|links)/[^/]+"),
    ("POST", r"/api/network/links/[^/]+/state"),
    ("POST", r"/api/failover/(settings|drill)"),
    ("POST", r"/api/quarantine/settings"),
    ("POST", r"/api/ml/.+"),
    ("ANY", r"/api/companies.*"),
    ("ANY", r"/api/notify/.*"),
    ("ANY", r"/api/ai/(settings|test)"),
    ("GET", r"/api/engineering/system"),
    ("POST", r"/api/analytics/(history|rollup)"),
    ("DELETE", r"/api/analytics/history"),
]
# Paths that name one device or node.
DEVICE_PATHS = [
    r"/api/devices/(?P<id>[^/]+)(/.*)?",
    r"/api/profiles/(?P<id>[^/]+)",
    r"/api/network/nodes/(?P<id>[^/]+)/state",
]


def _is_platform_only(method: str, path: str) -> bool:
    return any((m == "ANY" or m == method) and re.fullmatch(p, path) for m, p in PLATFORM_ONLY)


def request_problem(scope: Scope, method: str, path: str, query: dict) -> str | None:
    """Why a company user may not make this request (None = allowed)."""
    if not scope.is_company:
        return None
    if _is_platform_only(method, path):
        return "This changes the shared network, which only the platform (provider) can do."
    for p in DEVICE_PATHS:
        m = re.fullmatch(p, path)
        if m:
            node = m.group("id").upper()
            if node in scope.hidden:
                return f"{node} belongs to another company."
            if p.startswith(r"/api/network/nodes") or p.startswith(r"/api/profiles"):
                # shared infrastructure nodes can be looked at, but not changed by one company
                if method != "GET" and node not in devices_of(scope.company_id):
                    return "This is shared network equipment; only the platform can change it."
    device = (query.get("device_id") or "").upper()
    if device and device in scope.hidden:
        return f"{device} belongs to another company."
    m = re.fullmatch(r"/api/simulation/attack/(?P<name>[^/]+)", path)
    if method == "POST" and m and not device:
        from app.attack_simulator import ATTACKS
        default = ATTACKS.get(m.group("name"), (None, ""))[1]
        if default in scope.hidden:
            return "Choose one of your company's devices for the simulated attack."
    return None
