"""
v2.1 (SOC stage 4): SOC roles and permissions.

The v1.1 roles (viewer < operator < admin) keep working. Four SOC roles are
added. They sit at the "operator" level for reads and simple writes, but every
change they make must also match a PERMISSION, so a tier-1 analyst can triage
alerts but cannot isolate a device or run a simulated attack.

  role          what it is for                              permissions
  viewer        read only                                   read
  soc_l1        tier 1: triage the alert queue              read, triage, hunt
  soc_l2        tier 2: investigate, open incidents,        read, triage, hunt, incident, intel, simulate,
                ask for containment                         contain_request
  soc_l3        tier 3: incident response                   + contain, contain_approve, playbook, respond
  soc_manager   SOC lead: everything above + detection      + rules
                rules
  operator      (v1.1) incident responder                   everything above except rules
  admin         everything                                  all

"contain" = quarantine / release a device directly (it is itself the human
decision). "contain_request" = ask for it: the request waits in Approvals for
someone with "contain_approve". The AI analyst can only create such requests
through a human (see ai_tools.py).
"""
import re

from sqlalchemy.orm import Session

from app import config
from app.models import AppFlag, User

ROLE_LABELS = {
    "viewer": "Viewer", "soc_l1": "SOC analyst L1", "soc_l2": "SOC analyst L2", "soc_l3": "SOC analyst L3 / responder",
    "soc_manager": "SOC manager", "operator": "Operator", "admin": "Administrator",
}
_L1 = {"read", "triage", "hunt"}
_L2 = _L1 | {"incident", "intel", "simulate", "contain_request"}
_L3 = _L2 | {"contain", "contain_approve", "playbook", "respond"}
ALL = _L3 | {"rules", "admin"}
PERMISSIONS = {
    "viewer": {"read"},
    "soc_l1": _L1,
    "soc_l2": _L2,
    "soc_l3": _L3,
    "soc_manager": _L3 | {"rules"},
    "operator": _L3,
    "admin": ALL,
}

# Changes that need a specific permission (checked after the role level).
PERM_RULES = [
    ("POST", r"/api/soc/alerts/\d+/action", "triage"),
    ("ANY", r"/api/hunt/queries(/\d+)?", "hunt"),
    ("POST", r"/api/incidents", "incident"),
    ("PUT", r"/api/incidents/\d+(/mitre)?", "incident"),
    ("POST", r"/api/incidents/\d+/(notes|phase|evidence)", "incident"),
    ("POST", r"/api/devices/[^/]+/(quarantine|release)", "contain"),
    ("POST", r"/api/approvals", "contain_request"),
    ("POST", r"/api/approvals/\d+/(approve|reject)", "contain_approve"),
    ("ANY", r"/api/intel/iocs(/\d+)?", "intel"),
    ("POST", r"/api/simulation/attack/.+", "simulate"),
    ("POST", r"/api/soc/rules/[^/]+/test", "simulate"),
    ("ANY", r"/api/soc/demo(/.*)?", "simulate"),
    ("POST", r"/api/incidents/\d+/playbooks(/.*)?", "playbook"),
    ("PUT", r"/api/soc/rules/[^/]+", "rules"),
]


def permissions_of(role: str | None) -> set[str]:
    return set(PERMISSIONS.get(role or "", set()))


def required_permission(method: str, path: str, level: str | None) -> str | None:
    """The permission this request needs (None = the role level alone decides)."""
    if level is None or method in ("GET", "HEAD", "OPTIONS"):
        return None
    for m, p, perm in PERM_RULES:
        if (m == "ANY" or m == method) and re.fullmatch(p, path):
            return perm
    if level == "operator":
        return "respond"  # any other operator-level change (network faults, failover, ML, exports...)
    return None


def has(role: str | None, perm: str) -> bool:
    return perm in permissions_of(role)


def seed_soc_users(db: Session) -> list[str]:
    """Create the four SOC demo accounts once (change the passwords after the first login)."""
    from app.auth import hash_password
    if not config.SEED_SOC_USERS or db.get(AppFlag, "soc_users_seeded") is not None:
        return []
    added = []
    for username, password, role in config.SOC_USERS:
        if db.get(User, username) is None:
            db.add(User(username=username, password_hash=hash_password(password), role=role))
            added.append(username)
    db.add(AppFlag(key="soc_users_seeded", value="1"))
    db.commit()
    return added
