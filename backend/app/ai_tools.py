"""
v2.1 (SOC stage 3): the AI SOC analyst's controlled tools.

The analyst never touches the database or the network directly. It can only
call the tools below. READ tools return data plus numbered evidence items.
ACTION tools are never executed by the AI: they are returned as *proposed
actions* that a person must confirm in the dashboard, and the confirmation
goes through the normal API with that person's role, permissions and audit
log (isolation additionally waits in Approvals).

  read     search_security_events, get_device_information, get_network_connections,
           analyze_alert, correlate_events, get_threat_intelligence,
           recommend_response, generate_incident_report
  action   create_incident, request_device_isolation

investigate() runs the tools for one alert / incident / question, numbers the
evidence E1, E2 ... and writes the answer:
  * with a configured language model: the model gets ONLY the evidence and must
    cite [E#] for every statement; citations that point to no evidence are
    removed and reported
  * without one (or if the model fails or cites nothing): a built-in analyst
    writes the same structure from the evidence
"""
import json
import re
from collections import Counter
from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import ai_assistant, intel, soc, tenancy
from app.models import AiInvestigation, Device, DeviceProfile, Incident, SecurityAlert, SecurityEvent, utcnow
from app.security_events import device_ip, is_external

TOOLS = [
    {"name": "search_security_events", "kind": "read", "description": "Search the security event store (Threat Hunting query language).",
     "params": {"query": "str", "hours": "int"}},
    {"name": "get_device_information", "kind": "read", "description": "Registry data, state, location and recent alerts of a device.",
     "params": {"device_id": "str"}},
    {"name": "get_network_connections", "kind": "read", "description": "Who the device talked to (addresses, ports, bytes) in a time window.",
     "params": {"device_id": "str", "minutes": "int"}},
    {"name": "analyze_alert", "kind": "read", "description": "Alert details with rule logic, MITRE technique and confidence.",
     "params": {"alert_id": "int"}},
    {"name": "correlate_events", "kind": "read", "description": "Other alerts and security events on the same device / addresses around the alert.",
     "params": {"alert_id": "int", "minutes": "int"}},
    {"name": "get_threat_intelligence", "kind": "read", "description": "Local IOC list + VirusTotal / AbuseIPDB / OTX if configured.",
     "params": {"value": "str"}},
    {"name": "recommend_response", "kind": "read", "description": "Playbook and response steps for the alert type.",
     "params": {"alert_id": "int"}},
    {"name": "generate_incident_report", "kind": "read", "description": "Markdown report of an incident.",
     "params": {"incident_id": "int"}},
    {"name": "create_incident", "kind": "action", "description": "Open an incident from an alert (a person must confirm).",
     "params": {"alert_id": "int"}},
    {"name": "request_device_isolation", "kind": "action",
     "description": "Ask for the (simulated) isolation of a device: goes to Approvals, a person with approval rights decides.",
     "params": {"device_id": "str", "reason": "str"}},
]
READ_TOOLS = {t["name"] for t in TOOLS if t["kind"] == "read"}


class Evidence:
    def __init__(self):
        self.items: list[dict] = []
        self._keys: dict[str, str] = {}

    def add(self, kind: str, ref: str, text: str, time: str | None = None, link: str | None = None) -> str:
        key = f"{kind}:{ref}"
        if key in self._keys:
            return self._keys[key]
        eid = f"E{len(self.items) + 1}"
        self._keys[key] = eid
        self.items.append({"id": eid, "kind": kind, "ref": ref, "text": text, "time": time, "link": link})
        return eid


def _hidden():
    return tenancy.current_hidden()


def _alert(db: Session, alert_id: int) -> SecurityAlert:
    a = db.get(SecurityAlert, int(alert_id))
    if a is None or a.device_id in _hidden():
        raise ValueError(f"alert #{alert_id} not found")
    return a


def _ev_text(e: SecurityEvent) -> str:
    where = f"{e.src_ip or '-'}{':' + str(e.src_port) if e.src_port else ''} → {e.dst_ip or '-'}{':' + str(e.dst_port) if e.dst_port else ''}"
    return f"{e.event_type} ({e.outcome}) {where} {e.protocol} {('user ' + e.username) if e.username else ''} {e.message}".strip()


# ------------------------------------------------------------------ read tools
def t_search_security_events(db, ev: Evidence, query: str = "", hours: int = 24, limit: int = 20):
    from app.routes.hunt import build
    rows = build(db, query, hours, None, None, None).order_by(SecurityEvent.id.desc()).limit(limit).all()
    for e in rows[:10]:
        ev.add("security_event", str(e.id), _ev_text(e), e.timestamp.isoformat() + "Z", f"#hunting?q=id:{e.id}")
    total = build(db, query, hours, None, None, None).count()
    return {"summary": f"{total} events match '{query}' in {hours} h", "count": total,
            "top_types": Counter(e.event_type for e in rows).most_common(5)}


def t_get_device_information(db, ev: Evidence, device_id: str):
    d = db.get(Device, device_id.upper())
    if d is None or d.device_id in _hidden():
        return {"summary": f"{device_id} is not a registered device", "registered": False}
    p = db.get(DeviceProfile, d.device_id)
    src = soc.source_of(db, d.device_id, {})
    open_alerts = db.query(SecurityAlert).filter(SecurityAlert.device_id == d.device_id, SecurityAlert.status == "open").count()
    ev.add("device", d.device_id, f"{d.device_id} {d.device_name} ({d.device_type}), {d.connection_type}, {d.location or 'no location'}; "
           f"status {d.status}, security {d.security_status}; {open_alerts} open alerts; source {src.upper()}; "
           f"simulated address {device_ip(d.device_id)}", link=f"#devices/{d.device_id}")
    return {"summary": f"{d.device_id} is {d.status} and {d.security_status}", "device": d.to_dict(), "source": src,
            "address": device_ip(d.device_id), "open_alerts": open_alerts,
            "location": {"lat": p.latitude, "lon": p.longitude} if p else None}


def t_get_network_connections(db, ev: Evidence, device_id: str, minutes: int = 60, around=None):
    t1 = around or utcnow()
    rows = (db.query(SecurityEvent).filter(SecurityEvent.device_id == device_id.upper(),
                                           SecurityEvent.timestamp >= t1 - timedelta(minutes=minutes),
                                           SecurityEvent.timestamp <= t1 + timedelta(minutes=5)).all())
    peers = Counter()
    nbytes = Counter()
    for e in rows:
        peer = e.dst_ip if e.src_ip == device_ip(e.device_id or "") else e.src_ip
        if not peer:
            continue
        key = f"{peer}:{e.dst_port or '-'}/{e.protocol}"
        peers[key] += 1
        nbytes[key] += e.bytes or 0
    external = [k for k in peers if is_external(k.split(":")[0])]
    for k in external[:5]:
        ev.add("connections", f"{device_id}-{k}", f"{device_id} ↔ {k}: {peers[k]} events, {nbytes[k]} bytes (external address)")
    return {"summary": f"{len(peers)} peers, {len(external)} external", "peers": [
        {"peer": k, "events": n, "bytes": nbytes[k], "external": k in external} for k, n in peers.most_common(10)]}


def t_analyze_alert(db, ev: Evidence, alert_id: int):
    a = _alert(db, alert_id)
    r = soc.enrich(db, [a])[0]
    rule = soc.RULES_BY_TYPE.get(a.alert_type)
    ev.add("alert", str(a.id), f"Alert #{a.id} [{a.severity}] {r['rule_id'] or a.alert_type} {r['rule_name']}: {a.description} "
           f"(confidence {round(r['confidence'] * 100)}%, {r['source'].upper()})", r["timestamp"], f"#alerts/{a.id}")
    if rule:
        ev.add("rule", rule["id"], f"Rule {rule['id']}: {rule['logic']}. {rule['explanation']}")
    return {"summary": f"#{a.id} {r['rule_name']} ({a.severity})", "alert": r, "rule": rule}


def t_correlate_events(db, ev: Evidence, alert_id: int, minutes: int = 30):
    a = _alert(db, alert_id)
    t0 = a.timestamp
    win = (t0 - timedelta(minutes=minutes), t0 + timedelta(minutes=minutes))
    related = []
    if a.device_id:
        related = (db.query(SecurityAlert).filter(SecurityAlert.device_id == a.device_id, SecurityAlert.id != a.id,
                                                  SecurityAlert.timestamp.between(*win)).order_by(SecurityAlert.timestamp).limit(10).all())
    for r in related:
        rule = soc.RULES_BY_TYPE.get(r.alert_type)
        ev.add("alert", str(r.id), f"Related alert #{r.id} [{r.severity}] {rule['id'] + ' ' if rule else ''}{r.alert_type}: {r.description}",
               r.timestamp.isoformat() + "Z", f"#alerts/{r.id}")
    events = []
    if a.device_id:
        events = (db.query(SecurityEvent).filter(SecurityEvent.device_id == a.device_id, SecurityEvent.category != "flow",
                                                 SecurityEvent.timestamp.between(*win)).order_by(SecurityEvent.id).limit(200).all())
    # keep the most telling events: first and last of each type, plus everything external
    picked = {}
    for e in events:
        picked.setdefault(e.event_type, [e, e])[1] = e
    chosen = {x.id: x for pair in picked.values() for x in pair}
    for e in sorted(chosen.values(), key=lambda x: x.id)[:12]:
        ev.add("security_event", str(e.id), _ev_text(e), e.timestamp.isoformat() + "Z", f"#hunting?q=id:{e.id}")
    addresses = sorted({ip for e in events for ip in (e.src_ip, e.dst_ip) if ip and is_external(ip)})
    by_type = Counter(e.event_type for e in events)
    return {"summary": f"{len(related)} related alerts, {len(events)} security events, {len(addresses)} external addresses",
            "related_alerts": [r.id for r in related], "event_types": dict(by_type), "external_addresses": addresses,
            "chain": [soc.RULES_BY_TYPE.get(r.alert_type, {}).get("name", r.alert_type) for r in [*related, a]]}


async def t_get_threat_intelligence(db, ev: Evidence, value: str):
    res = await intel.lookup(db, value)
    parts = [f"verdict {res['verdict']}"]
    if res.get("local"):
        l0 = res["local"][0]
        parts.append(f"local IOC '{l0['threat']}' (confidence {l0['confidence']}%, {l0['origin']})")
    for x in res.get("external", []):
        if x.get("error"):
            parts.append(f"{x['provider']}: error")
        elif x.get("found") is False:
            parts.append(f"{x['provider']}: unknown")
        else:
            parts.append(f"{x['provider']}: {x.get('verdict')}")
    if res.get("external_skipped"):
        parts.append(f"external lookup skipped ({res['external_skipped']})")
    ev.add("intel", value, f"Threat intel for {value}: " + "; ".join(parts), link=f"#intel?value={value}")
    return {"summary": f"{value}: {res['verdict']}", **res}


def t_recommend_response(db, ev: Evidence, alert_id: int):
    from app import playbooks
    a = _alert(db, alert_id)
    ids = playbooks.suggest([a.alert_type])
    pb = playbooks.PLAYBOOKS[ids[0]]
    ev.add("playbook", ids[0], f"Playbook {ids[0]} '{pb['name']}': " + " → ".join(s["title"] for s in pb["steps"]))
    return {"summary": f"{ids[0]} {pb['name']}", "playbooks": ids, "steps": [s["title"] for s in pb["steps"]]}


def t_generate_incident_report(db, ev: Evidence, incident_id: int):
    from app.incident_workflow import report_markdown
    inc = db.get(Incident, int(incident_id))
    if inc is None or (inc.device_id and inc.device_id in _hidden()):
        raise ValueError(f"incident #{incident_id} not found")
    text = report_markdown(db, inc)
    ev.add("incident", str(inc.id), f"Incident #{inc.id} {inc.title} ({inc.status})", link=f"#incidents/{inc.id}")
    return {"summary": f"report of incident #{inc.id} ({len(text)} characters)", "markdown": text}


READ_FUNCS = {
    "search_security_events": t_search_security_events, "get_device_information": t_get_device_information,
    "get_network_connections": t_get_network_connections, "analyze_alert": t_analyze_alert,
    "correlate_events": t_correlate_events, "get_threat_intelligence": t_get_threat_intelligence,
    "recommend_response": t_recommend_response, "generate_incident_report": t_generate_incident_report,
}


async def run_tool(db: Session, name: str, args: dict, ev: Evidence | None = None) -> dict:
    """Run one READ tool (used by investigate() and by the analyst from the tool panel)."""
    if name not in READ_FUNCS:
        raise ValueError(f"'{name}' is not a read tool (actions need a person: see proposed actions)")
    ev = ev or Evidence()
    fn = READ_FUNCS[name]
    import inspect
    res = fn(db, ev, **args)
    if inspect.isawaitable(res):
        res = await res
    return {"tool": name, "args": args, **res, "evidence": ev.items}


# ------------------------------------------------------------------ investigation
SYSTEM = """You are the AI SOC analyst of CyberShield SOC, a university project with a SIMULATED satellite-5G IoT network.
Write a short investigation in Markdown with exactly these sections:
**Summary**, **Findings**, **Assessment**, **MITRE ATT&CK**, **Recommended actions**, **Limits**.
Rules:
- Use ONLY the evidence items given. Every finding must end with its citation(s) like [E3] or [E2][E5].
- If the evidence does not show something, say it is unknown. Never invent addresses, devices, numbers or techniques.
- Actions (opening an incident, isolating a device) are only proposals: a human decides.
- Remember the data source labels: SIM = simulator, LAB = real test board. Never call simulated data real-world."""


def _offline_answer(focus: dict, ev: Evidence, tools: dict) -> str:
    def cite(kind, ref=None):
        return "".join(f"[{e['id']}]" for e in ev.items if e["kind"] == kind and (ref is None or e["ref"] == ref))

    a = tools.get("analyze_alert", {}).get("alert")
    corr = tools.get("correlate_events", {})
    lines = ["**Summary**"]
    if a:
        lines.append(f"Alert #{a['id']} ({a['rule_name']}, {a['severity']}) on {a['device_id'] or 'the network'}"
                     f" {cite('alert', str(a['id']))}. Data source: {a['source'].upper()}.")
    elif focus.get("question"):
        lines.append(f"Question: {focus['question']}. Results from the security event store below.")
    lines += ["", "**Findings**"]
    if a:
        rule = tools["analyze_alert"].get("rule")
        if rule:
            lines.append(f"- Detection logic: {rule['logic']} {cite('rule', rule['id'])}")
    if corr.get("related_alerts"):
        lines.append(f"- {len(corr['related_alerts'])} related alert(s) on the same device in ±30 min: "
                     + ", ".join(f"#{i}" for i in corr["related_alerts"]) + " "
                     + "".join(f"[{e['id']}]" for e in ev.items if e["kind"] == "alert" and int(e["ref"]) in corr["related_alerts"]))
        lines.append(f"- Sequence: {' → '.join(corr['chain'])}")
    if corr.get("event_types"):
        lines.append("- Security events around the alert: " + ", ".join(f"{k} ×{v}" for k, v in corr["event_types"].items())
                     + " " + cite("security_event"))
    conns = tools.get("get_network_connections", {}).get("peers", [])
    for p in [p for p in conns if p["external"]][:3]:
        lines.append(f"- External peer {p['peer']}: {p['events']} events, {p['bytes']} bytes "
                     + "".join(f"[{e['id']}]" for e in ev.items if e["kind"] == "connections" and e["ref"].endswith(p["peer"])))
    for e in ev.items:
        if e["kind"] == "intel":
            lines.append(f"- {e['text']} [{e['id']}]")
    dev = tools.get("get_device_information", {})
    if dev.get("device"):
        lines.append(f"- Asset: {dev['device']['device_id']} {dev['device']['device_name']}, {dev['device']['security_status']}, "
                     f"{dev['open_alerts']} open alerts {cite('device')}")
    if "search_security_events" in tools:
        s = tools["search_security_events"]
        lines.append(f"- {s['summary']} {cite('security_event')}")
    lines += ["", "**Assessment**"]
    if a:
        corroborated = bool(corr.get("related_alerts")) or any(e["kind"] == "intel" and "malicious" in e["text"] for e in ev.items)
        level = "likely a true positive" if a["confidence"] >= 0.7 and corroborated else (
            "plausible, needs confirmation" if a["confidence"] >= 0.5 else "low confidence, could be a false positive")
        lines.append(f"Rule confidence {round(a['confidence'] * 100)}%{', corroborated by other evidence' if corroborated else ''}: "
                     f"**{level}** {cite('alert', str(a['id']))}.")
    else:
        lines.append("No single alert in focus; see the findings.")
    lines += ["", "**MITRE ATT&CK**"]
    techniques = []
    for e in ev.items:
        if e["kind"] == "alert":
            m = re.search(r"\b(CS-\d{3})\b", e["text"])
            r = next((x for x in soc.rule_catalog() if m and x["id"] == m.group(1)), None)
            if r and r["mitre"] and r["mitre"]["id"] not in [t[0] for t in techniques]:
                techniques.append((r["mitre"]["id"], f"{r['mitre']['id']} {r['mitre']['name']} ({r['mitre']['tactic']}) [{e['id']}]"))
    lines += [f"- {t[1]}" for t in techniques] or ["- no ATT&CK technique for these detections"]
    lines += ["", "**Recommended actions**"]
    rec = tools.get("recommend_response")
    if rec:
        lines.append(f"- Follow playbook {rec['summary']} {cite('playbook')}: " + "; ".join(rec["steps"][:5]) + ".")
    if a and a["device_id"] and a["severity"] in ("high", "critical"):
        lines.append(f"- Proposed: isolate {a['device_id']} (needs approval) and open an incident (needs confirmation).")
    lines += ["", "**Limits**", "- Based only on the evidence listed; devices, attacks and addresses are simulated (SIM) unless marked LAB."]
    return "\n".join(lines)


def _check_citations(text: str, ev: Evidence) -> tuple[str, list[str], int]:
    valid = {e["id"] for e in ev.items}
    bad = []

    def fix(m):
        if m.group(1) in valid:
            return m.group(0)
        bad.append(m.group(1))
        return ""

    cleaned = re.sub(r"\[(E\d+)\]", fix, text)
    used = len(set(re.findall(r"\[(E\d+)\]", cleaned)))
    return cleaned, sorted(set(bad)), used


async def investigate(db: Session, user: str, alert_id: int | None = None, incident_id: int | None = None,
                      question: str | None = None, attach: bool = True) -> dict:
    ev = Evidence()
    calls = []
    tools: dict = {}
    focus = {"alert_id": alert_id, "incident_id": incident_id, "question": question}
    inc = None
    if incident_id:
        inc = db.get(Incident, int(incident_id))
        if inc is None or (inc.device_id and inc.device_id in _hidden()):
            raise ValueError(f"incident #{incident_id} not found")
        alert_id = alert_id or inc.alert_id
        ev.add("incident", str(inc.id), f"Incident #{inc.id} {inc.title} ({inc.severity}, {inc.status})", link=f"#incidents/{inc.id}")

    async def call(name, **args):
        try:
            res = await run_tool(db, name, args, ev)
            tools[name] = res
            calls.append({"tool": name, "args": {k: v for k, v in args.items() if k != "around"}, "summary": res.get("summary", "")})
        except Exception as exc:
            calls.append({"tool": name, "args": {k: v for k, v in args.items() if k != "around"}, "error": str(exc)[:200]})

    a = None
    if alert_id:
        a = _alert(db, alert_id)
        await call("analyze_alert", alert_id=a.id)
        if a.device_id:
            await call("get_device_information", device_id=a.device_id)
        await call("correlate_events", alert_id=a.id)
        if a.device_id:
            await call("get_network_connections", device_id=a.device_id, minutes=30, around=a.timestamp)
        ips = list(tools.get("correlate_events", {}).get("external_addresses", []))[:3]
        for m in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", a.description):
            if m not in ips and is_external(m):
                ips.append(m)
        for ip in ips[:3]:
            await call("get_threat_intelligence", value=ip)
        await call("recommend_response", alert_id=a.id)
    if question:
        q = question
        dev = re.search(r"\b([A-Z]+-\d{3,})\b", question.upper())
        ip = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", question)
        query = f"device:{dev.group(1)}" if dev else (f"ip:{ip.group(0)}" if ip else "-category:flow")
        await call("search_security_events", query=query, hours=24)
        if dev and not a:
            await call("get_device_information", device_id=dev.group(1))
        if ip and not a:
            await call("get_threat_intelligence", value=ip.group(0))
    else:
        q = f"Investigate alert #{alert_id}" if alert_id else f"Investigate incident #{incident_id}"

    proposed = []
    if a:
        open_inc = db.query(Incident).filter(or_(Incident.alert_id == a.id), Incident.status != "resolved").first()
        if not open_inc and not inc:
            proposed.append({"tool": "create_incident", "args": {"alert_id": a.id},
                             "label": f"Open an incident from alert #{a.id}", "needs": "incident"})
        d = db.get(Device, a.device_id) if a.device_id else None
        if d and d.security_status != "quarantined" and a.severity in ("high", "critical"):
            proposed.append({"tool": "request_device_isolation",
                             "args": {"device_id": d.device_id, "reason": f"AI analyst: {a.alert_type} (alert #{a.id})",
                                      "alert_id": a.id, "incident_id": (inc.id if inc else (open_inc.id if open_inc else None))},
                             "label": f"Request isolation of {d.device_id} (goes to Approvals)", "needs": "contain_request"})

    provider = "offline"
    note = None
    answer = None
    if ai_assistant.is_configured():
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Task: {q}\n\nEvidence (JSON):\n" +
                     json.dumps([{k: e[k] for k in ("id", "kind", "text", "time")} for e in ev.items], ensure_ascii=False)[:14000]
                     + "\n\nTool results:\n" + json.dumps(calls, ensure_ascii=False)[:3000]}]
        try:
            text = await ai_assistant.ask_llm(messages)
            text, bad, used = _check_citations(text, ev)
            if used == 0:
                note = "The language model cited no evidence, so its answer was discarded and the built-in analyst answered."
            else:
                answer, provider = text, ai_assistant.active()["provider"]
                if bad:
                    note = f"Removed citations to evidence that does not exist: {', '.join(bad)}."
        except Exception as exc:
            note = f"AI provider unavailable ({str(exc)[:120]}); the built-in analyst answered."
    if answer is None:
        answer = _offline_answer(focus, ev, tools)
    row = AiInvestigation(alert_id=a.id if a else None, incident_id=inc.id if inc else None, question=q, answer=answer,
                          evidence=json.dumps(ev.items), tools=json.dumps(calls), actions=json.dumps(proposed),
                          provider=provider, created_by=user)
    db.add(row)
    db.flush()
    if inc and attach:
        from app.incident_workflow import add_evidence
        first = answer.split("\n")[1] if "\n" in answer else answer
        add_evidence(db, inc, "ai_analysis", str(row.id), f"AI analyst investigation #{row.id} ({provider}): {first[:300]}",
                     {"investigation_id": row.id}, user)
    db.commit()
    return {"id": row.id, "question": q, "answer": answer, "evidence": ev.items, "tool_calls": calls,
            "proposed_actions": proposed, "source": provider, "note": note,
            "tools_available": TOOLS}
