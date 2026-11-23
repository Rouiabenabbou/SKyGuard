"""
v2.1 (SOC stage 3): threat intelligence.

* Local IOC list (table iocs): addresses, domains, file hashes and URLs that
  analysts (or a playbook) marked as malicious. Every security event is checked
  against the active IP indicators (rule CS-018).
* Enrichment through free external services, only when their API key is set in
  .env (keys never reach the browser):
      VIRUSTOTAL_API_KEY   https://www.virustotal.com  (IP, domain, hash, URL)
      ABUSEIPDB_API_KEY    https://www.abuseipdb.com   (IP)
      OTX_API_KEY          https://otx.alienvault.com  (IP, domain, hash)
  Answers are cached 24 h (table intel_cache) to stay inside the free quota.
  Private addresses and the documentation ranges used by the simulator are
  never sent out: no external service knows them, and internal addresses
  should not leave the SOC.

The demo IOCs seeded on first start use documentation addresses (RFC 5737)
and are labelled "demo seed"; they are not real threat data.
"""
import ipaddress
import json
import re
import time
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app import config
from app.models import AppFlag, IntelCache, Ioc, utcnow

DEMO_IOCS = [
    ("ip", "198.51.100.66", "Botnet command-and-control server", 90, "c2,botnet,iot",
     "Demo indicator (documentation address). The botnet-beaconing scenario calls home to it."),
    ("ip", "198.51.100.23", "Data exfiltration drop server", 75, "exfiltration",
     "Demo indicator (documentation address) used by the data-exfiltration scenario."),
    ("domain", "update-iot-firmware.example", "Fake firmware update site", 70, "phishing,firmware",
     "Demo indicator on the reserved .example domain."),
    ("hash", "44d88612fea8a8f36de82e1278abb02f", "EICAR anti-virus test file (MD5)", 100, "test",
     "The harmless standard test file that every anti-virus flags; useful to test enrichment."),
]

# ------------------------------------------------------------------ local list
_ip_iocs: dict[str, dict] = {}
_loaded_at = 0.0


def kind_of(value: str) -> str | None:
    v = value.strip()
    try:
        ipaddress.ip_address(v)
        return "ip"
    except ValueError:
        pass
    if re.fullmatch(r"[A-Fa-f0-9]{32}|[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}", v):
        return "hash"
    if re.match(r"^https?://", v):
        return "url"
    if re.fullmatch(r"(?=.{3,253}$)([A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}", v):
        return "domain"
    return None


def reload(db: Session | None = None) -> None:
    global _loaded_at
    from app.database import SessionLocal
    own = db is None
    db = db or SessionLocal()
    try:
        now = utcnow()
        rows = db.query(Ioc).filter(Ioc.active.is_(True), Ioc.kind == "ip").all()
        _ip_iocs.clear()
        for r in rows:
            if r.expires_at is None or r.expires_at > now:
                _ip_iocs[r.value] = {"id": r.id, "threat": r.threat, "confidence": r.confidence, "origin": r.origin}
        _loaded_at = time.time()
    finally:
        if own:
            db.close()


def match(ip: str | None) -> dict | None:
    if not ip:
        return None
    if time.time() - _loaded_at > 30:
        try:
            reload()
        except Exception:
            return None
    return _ip_iocs.get(ip)


def seed_demo_iocs(db: Session) -> int:
    if not config.SEED_DEMO_IOCS or db.get(AppFlag, "demo_iocs_seeded") is not None:
        return 0
    for kind, value, threat, conf, tags, desc in DEMO_IOCS:
        if not db.query(Ioc).filter(Ioc.value == value).first():
            db.add(Ioc(kind=kind, value=value, threat=threat, confidence=conf, tags=tags, origin="demo seed",
                       description=desc, created_by="system"))
    db.add(AppFlag(key="demo_iocs_seeded", value="1"))
    db.commit()
    reload(db)
    return len(DEMO_IOCS)


def add_ioc(db: Session, kind: str, value: str, threat: str, confidence: int, tags: str, origin: str,
            description: str, username: str, days: int | None = None) -> Ioc:
    existing = db.query(Ioc).filter(Ioc.value == value, Ioc.active.is_(True)).first()
    if existing:
        return existing
    row = Ioc(kind=kind, value=value, threat=threat, confidence=confidence, tags=tags, origin=origin,
              description=description, created_by=username,
              expires_at=utcnow() + timedelta(days=days) if days else None)
    db.add(row)
    db.commit()
    reload(db)
    return row


# ------------------------------------------------------------------ external
def providers() -> list[dict]:
    return [
        {"id": "virustotal", "name": "VirusTotal", "configured": bool(config.VIRUSTOTAL_API_KEY), "kinds": ["ip", "domain", "hash", "url"],
         "env": "VIRUSTOTAL_API_KEY", "site": "https://www.virustotal.com"},
        {"id": "abuseipdb", "name": "AbuseIPDB", "configured": bool(config.ABUSEIPDB_API_KEY), "kinds": ["ip"],
         "env": "ABUSEIPDB_API_KEY", "site": "https://www.abuseipdb.com"},
        {"id": "otx", "name": "AlienVault OTX", "configured": bool(config.OTX_API_KEY), "kinds": ["ip", "domain", "hash"],
         "env": "OTX_API_KEY", "site": "https://otx.alienvault.com"},
    ]


def _not_shareable(kind: str, value: str) -> str | None:
    if kind != "ip":
        return None
    a = ipaddress.ip_address(value)
    from app.security_events import is_documentation
    if is_documentation(value):
        return "documentation address (used by the simulator): no external service knows it"
    if a.is_private or a.is_loopback or a.is_reserved or a.is_link_local:
        return "private address: kept inside the SOC"
    return None


async def _virustotal(client, kind, value):
    import base64
    path = {"ip": f"ip_addresses/{value}", "domain": f"domains/{value}", "hash": f"files/{value}",
            "url": "urls/" + base64.urlsafe_b64encode(value.encode()).decode().strip("=")}[kind]
    r = await client.get(f"https://www.virustotal.com/api/v3/{path}", headers={"x-apikey": config.VIRUSTOTAL_API_KEY})
    if r.status_code == 404:
        return {"found": False}
    r.raise_for_status()
    attrs = r.json().get("data", {}).get("attributes", {})
    stats = attrs.get("last_analysis_stats", {})
    return {"found": True, "malicious": stats.get("malicious", 0), "suspicious": stats.get("suspicious", 0),
            "harmless": stats.get("harmless", 0), "reputation": attrs.get("reputation"),
            "country": attrs.get("country"), "owner": attrs.get("as_owner"),
            "verdict": "malicious" if stats.get("malicious", 0) >= 3 else ("suspicious" if stats.get("malicious", 0) or stats.get("suspicious", 0) else "clean")}


async def _abuseipdb(client, kind, value):
    r = await client.get("https://api.abuseipdb.com/api/v2/check", params={"ipAddress": value, "maxAgeInDays": 90},
                         headers={"Key": config.ABUSEIPDB_API_KEY, "Accept": "application/json"})
    r.raise_for_status()
    d = r.json().get("data", {})
    score = d.get("abuseConfidenceScore", 0)
    return {"found": True, "abuse_score": score, "reports": d.get("totalReports"), "country": d.get("countryCode"),
            "isp": d.get("isp"), "usage": d.get("usageType"), "last_reported": d.get("lastReportedAt"),
            "verdict": "malicious" if score >= 75 else ("suspicious" if score >= 25 else "clean")}


async def _otx(client, kind, value):
    section = {"ip": "IPv4", "domain": "domain", "hash": "file"}[kind]
    r = await client.get(f"https://otx.alienvault.com/api/v1/indicators/{section}/{value}/general",
                         headers={"X-OTX-API-KEY": config.OTX_API_KEY})
    if r.status_code == 404:
        return {"found": False}
    r.raise_for_status()
    d = r.json()
    pulses = d.get("pulse_info", {}).get("count", 0)
    return {"found": True, "pulses": pulses, "country": d.get("country_name"),
            "names": [p.get("name") for p in d.get("pulse_info", {}).get("pulses", [])[:3]],
            "verdict": "malicious" if pulses >= 3 else ("suspicious" if pulses else "clean")}


CALLS = {"virustotal": _virustotal, "abuseipdb": _abuseipdb, "otx": _otx}


async def lookup(db: Session, value: str, use_external: bool = True) -> dict:
    """Local IOC match + external reputation (cached). Never raises for a provider error."""
    value = value.strip()
    kind = kind_of(value)
    if kind is None:
        return {"value": value, "kind": None, "error": "Not an IP address, domain, URL or MD5/SHA1/SHA256 hash."}
    local = [r.to_dict() for r in db.query(Ioc).filter(Ioc.value == value).all()]
    out = {"value": value, "kind": kind, "local": local, "external": [], "verdict": None}
    reason = _not_shareable(kind, value)
    if reason:
        out["external_skipped"] = reason
    elif use_external:
        async with httpx.AsyncClient(timeout=config.INTEL_TIMEOUT) as client:
            for p in providers():
                if not p["configured"] or kind not in p["kinds"]:
                    continue
                key = f"{p['id']}:{value}"[:340]
                cached = db.get(IntelCache, key)
                if cached and cached.fetched_at > utcnow() - timedelta(hours=24):
                    out["external"].append({"provider": p["name"], "cached": True, **json.loads(cached.data)})
                    continue
                try:
                    data = await CALLS[p["id"]](client, kind, value)
                    row = cached or IntelCache(key=key)
                    row.data, row.fetched_at = json.dumps(data), utcnow()
                    db.merge(row)
                    db.commit()
                    out["external"].append({"provider": p["name"], "cached": False, **data})
                except Exception as exc:
                    msg = str(exc)
                    for secret in (config.VIRUSTOTAL_API_KEY, config.ABUSEIPDB_API_KEY, config.OTX_API_KEY):
                        if secret:
                            msg = msg.replace(secret, "***")
                    out["external"].append({"provider": p["name"], "error": msg[:160]})
    verdicts = [x.get("verdict") for x in out["external"] if x.get("verdict")]
    active_local = [x for x in local if x["active"]]
    if active_local:
        out["verdict"] = "malicious" if max(x["confidence"] for x in active_local) >= 60 else "suspicious"
    elif "malicious" in verdicts:
        out["verdict"] = "malicious"
    elif "suspicious" in verdicts:
        out["verdict"] = "suspicious"
    elif verdicts:
        out["verdict"] = "clean"
    else:
        out["verdict"] = "unknown"
    return out
