import { useEffect, useMemo, useRef, useState } from "react";
import { Bell, BellOff, CircleUser, KeyRound, Menu, Search, Volume2, VolumeX } from "lucide-react";
import { useAuth } from "../../auth.jsx";
import { api } from "../../services/api.js";
import { alarmEnabled, playAlarm, setAlarmEnabled } from "../../services/alarm.js";
import { alertLabel } from "../AlertsPanel.jsx";
import { NAV, PAGES } from "./navigation.js";
import { ENVIRONMENTS, setEnvironment, useEnvironment } from "../../services/environment.js";

const ROLE_HINT = {
  viewer: "read only", operator: "can respond to incidents", admin: "full control",
  soc_l1: "triage alerts, hunt", soc_l2: "investigate, open incidents, request containment",
  soc_l3: "respond, approve containment, run playbooks", soc_manager: "SOC lead: everything + detection rules",
};

// v2.1: two-factor login (TOTP) set up from the account menu.
function TwoFactor({ user, onChanged }) {
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState(null);
  const act = async (fn, ok) => {
    try {
      await fn();
      setMsg({ ok: true, text: ok });
      setCode("");
      onChanged();
      return true;
    } catch (e) {
      setMsg({ ok: false, text: e.message });
      return false;
    }
  };
  return (
    <div className="mfa-box">
      <div className="small"><KeyRound size={13} /> <b>Two-factor login</b> · {user.mfa_enabled ? <span className="tone-ok">on</span> : <span className="muted">off</span>}
        {user.mfa_required && !user.mfa_enabled && <span className="tone-bad"> · required for your role</span>}</div>
      {!user.mfa_enabled && !setup && (
        <button type="button" className="btn btn-small" onClick={() => api.mfaSetup().then(setSetup).catch((e) => setMsg({ ok: false, text: e.message }))}>Set up</button>
      )}
      {setup && !user.mfa_enabled && (
        <>
          <div className="small muted">In your authenticator app choose “enter a setup key” and type:</div>
          <code className="mfa-secret">{setup.secret.match(/.{1,4}/g).join(" ")}</code>
          <div className="small muted">Or open on the phone: <a href={setup.otpauth_uri}>otpauth link</a>. Then enter the 6-digit code:</div>
          <div className="button-row">
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={7} placeholder="123456" style={{ width: 100 }} />
            <button type="button" className="btn btn-small btn-primary" disabled={code.trim().length < 6}
                    onClick={() => act(() => api.mfaEnable(code.trim()), "Two-factor login is on.").then((done) => done && setSetup(null))}>Turn on</button>
          </div>
        </>
      )}
      {user.mfa_enabled && !user.mfa_required && (
        <div className="button-row">
          <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={7} placeholder="code" style={{ width: 90 }} />
          <button type="button" className="btn btn-small" disabled={code.trim().length < 6}
                  onClick={() => act(() => api.mfaDisable(code.trim()), "Two-factor login is off.")}>Turn off</button>
        </div>
      )}
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </div>
  );
}

function EnvironmentSelect() {
  const env = useEnvironment();
  return (
    <select className={`env-select env-${env}`} value={env} onChange={(e) => setEnvironment(e.target.value)} aria-label="Data source"
            title="Which data source the SOC pages show. Production: no real infrastructure is connected in this project.">
      {ENVIRONMENTS.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
    </select>
  );
}

function useOutside(ref, close) {
  useEffect(() => {
    const on = (e) => ref.current && !ref.current.contains(e.target) && close();
    document.addEventListener("pointerdown", on);
    return () => document.removeEventListener("pointerdown", on);
  }, [ref, close]);
}

// Global search over what this user can see: modules, devices, network nodes, alerts, incidents.
function GlobalSearch({ devices, network, alerts, onNavigate, can }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [incidents, setIncidents] = useState([]);
  const [sel, setSel] = useState(0);
  const box = useRef(null);
  useOutside(box, () => setOpen(false));
  useEffect(() => {
    if (open && q.length >= 2) api.incidents().then((r) => setIncidents(r.incidents)).catch(() => {});
  }, [open, q.length >= 2]); // eslint-disable-line react-hooks/exhaustive-deps

  const results = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (n.length < 2) return [];
    const has = (...xs) => xs.some((x) => String(x ?? "").toLowerCase().includes(n));
    const out = [];
    NAV.flatMap((g) => g.items).filter((i) => (!i.role || can(i.role)) && has(i.label)).forEach((i) => out.push({ k: "Module", label: i.label, go: i.id }));
    Object.values(devices).filter((d) => has(d.device_id, d.device_name, d.device_type, d.location)).slice(0, 8)
      .forEach((d) => out.push({ k: "Device", label: `${d.device_id} · ${d.device_name}`, go: `devices/${d.device_id}` }));
    (network?.nodes ?? []).filter((x) => x.node_type !== "iot_device" && has(x.node_id, x.name)).slice(0, 5)
      .forEach((x) => out.push({ k: "Network", label: `${x.node_id} · ${x.name}`, go: "network" }));
    alerts.filter((a) => has(`#${a.id}`, a.id, a.alert_type, alertLabel(a.alert_type), a.device_id, a.description)).slice(0, 8)
      .forEach((a) => out.push({ k: "Alert", label: `#${a.id} ${alertLabel(a.alert_type)} · ${a.device_id ?? "network"}`, go: `alerts/${a.id}` }));
    incidents.filter((i) => has(`#${i.id}`, i.title, i.device_id)).slice(0, 5)
      .forEach((i) => out.push({ k: "Incident", label: `#${i.id} ${i.title}`, go: `incidents/${i.id}` }));
    return out.slice(0, 20);
  }, [q, devices, network, alerts, incidents, can]);

  const go = (r) => {
    onNavigate(r.go);
    setOpen(false);
    setQ("");
  };

  return (
    <div className="global-search" ref={box}>
      <Search size={14} />
      <input value={q} placeholder="Search devices, alerts, incidents, modules…" aria-label="Global search"
             onChange={(e) => { setQ(e.target.value); setOpen(true); setSel(0); }} onFocus={() => setOpen(true)}
             onKeyDown={(e) => {
               if (e.key === "ArrowDown") setSel((s) => Math.min(s + 1, results.length - 1));
               if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
               if (e.key === "Enter" && results[sel]) go(results[sel]);
               if (e.key === "Escape") setOpen(false);
             }} />
      {open && q.trim().length >= 2 && (
        <div className="search-results">
          {results.length === 0 && <div className="empty">No match.</div>}
          {results.map((r, i) => (
            <div key={`${r.k}-${r.label}`} className={`dd-item ${i === sel ? "on" : ""}`} onMouseEnter={() => setSel(i)} onClick={() => go(r)}>
              <span className="k">{r.k}</span><span>{r.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Notifications({ alerts, onNavigate }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useOutside(box, () => setOpen(false));
  const urgent = alerts.filter((a) => a.status === "open" && (a.severity === "high" || a.severity === "critical"));
  const latest = alerts.filter((a) => a.status === "open").slice(0, 12);
  return (
    <div style={{ position: "relative" }} ref={box}>
      <button className="icon-btn" aria-label="Notifications" onClick={() => setOpen((o) => !o)}>
        {urgent.length ? <Bell size={17} /> : <BellOff size={17} />}
        {urgent.length > 0 && <span className="dot-count">{urgent.length > 99 ? "99+" : urgent.length}</span>}
      </button>
      {open && (
        <div className="dropdown">
          <div className="dd-head"><span>Open alerts</span><a href="#alerts" onClick={() => setOpen(false)}>Alert Center</a></div>
          {latest.length === 0 && <div className="empty">No open alerts.</div>}
          {latest.map((a) => (
            <div key={a.id} className="dd-item" onClick={() => { onNavigate(`alerts/${a.id}`); setOpen(false); }}>
              <span className={`sev sev-${a.severity}`}>{a.severity}</span>
              <span style={{ flex: 1 }}>{alertLabel(a.alert_type)} · {a.device_id ?? "network"}<br />
                <span className="muted small">#{a.id} · {new Date(a.timestamp).toLocaleTimeString()}</span></span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Account() {
  const { user, logout, authEnabled, refresh } = useAuth();
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState({ old: "", next: "" });
  const [msg, setMsg] = useState(null);
  const box = useRef(null);
  useOutside(box, () => setOpen(false));
  if (!user) return null;
  async function changePassword(e) {
    e.preventDefault();
    try {
      await api.changePassword(pw.old, pw.next);
      setMsg({ ok: true, text: "Password changed." });
      setPw({ old: "", next: "" });
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    }
  }
  return (
    <div style={{ position: "relative" }} ref={box}>
      <button className="icon-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
        <CircleUser size={17} /> <span className="hide-sm">{user.username}</span>
        <span className={`role-badge role-${user.role}`}>{user.role.replace("soc_", "")}</span>
      </button>
      {open && (
        <div className="dropdown" style={{ padding: 12 }}>
          <div className="small"><b>{user.username}</b> · {user.role_label ?? user.role} ({ROLE_HINT[user.role]})</div>
          <div className="small muted">{user.company_name ? `Company: ${user.company_name} (sees only its devices)` : "Platform (provider): sees every company"}</div>
          {authEnabled ? (
            <form className="config-form" onSubmit={changePassword}>
              <label><span>Current password</span>
                <input type="password" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} required /></label>
              <label><span>New password (8+ characters, letters and a number)</span>
                <input type="password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} required /></label>
              {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
              <div className="config-actions">
                <button className="btn btn-small">Change password</button>
                <button type="button" className="btn btn-small btn-danger" onClick={logout}>Log out</button>
              </div>
            </form>
          ) : <div className="muted small">Login is switched off (AUTH_ENABLED=false).</div>}
          {authEnabled && <TwoFactor user={user} onChanged={refresh} />}
        </div>
      )}
    </div>
  );
}

export default function Topbar({ page, connected, latencyMs, devices, network, alerts, onNavigate, onMenu }) {
  const [alarm, setAlarm] = useState(alarmEnabled);
  const info = PAGES[page];
  const list = Object.values(devices);
  const lab = list.filter((d) => d.simulated === false).length;
  return (
    <header className="topbar">
      <button className="icon-btn" aria-label="Toggle navigation" onClick={onMenu}><Menu size={18} /></button>
      <div>
        <div className="page-title">{info?.label}</div>
      </div>
      <span className="crumb">{info?.group}</span>
      <div className="tb-spacer" />
      <span className="cloud-chip" title="Deployment target: Huawei Cloud (ECS, RDS, IoTDA, ModelArts)"><i />Huawei Cloud · AP-Singapore</span>
      <GlobalSearch devices={devices} network={network} alerts={alerts} onNavigate={onNavigate} can={useAuth().can} />
      <EnvironmentSelect />
      <span className="env-badge env-sim" title="Telemetry from the built-in simulator">SIMULATION {list.length - lab}</span>
      {lab > 0 && <span className="env-badge env-lab hide-sm" title="Telemetry from real test boards">LAB {lab}</span>}
      <span className="conn" title={connected ? "WebSocket to the backend is open" : "No connection to the backend"}>
        <span className="status-dot" style={{ background: connected ? "var(--ok)" : "var(--bad)" }} />
        <span className="conn-label">{connected ? `Live${latencyMs != null ? ` · ${latencyMs} ms` : ""}` : "Offline"}</span>
      </span>
      <button className="icon-btn" title={alarm ? "Browser siren on attacks: on" : "Browser siren on attacks: off"} aria-label="Siren"
              onClick={() => { setAlarmEnabled(!alarm); setAlarm(!alarm); if (!alarm) playAlarm("high", 1); }}>
        {alarm ? <Volume2 size={17} /> : <VolumeX size={17} />}
      </button>
      <Notifications alerts={alerts} onNavigate={onNavigate} />
      <Account />
    </header>
  );
}
