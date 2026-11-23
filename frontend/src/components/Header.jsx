import { useState } from "react";
import { useAuth } from "../auth.jsx";
import { api } from "../services/api.js";
import { alarmEnabled, playAlarm, setAlarmEnabled } from "../services/alarm.js";

const ROLE_HINT = {
  viewer: "read only",
  operator: "can respond to incidents",
  admin: "full control",
};

export default function Header({ connected, latencyMs }) {
  const { user, logout, authEnabled } = useAuth();
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState({ old: "", next: "" });
  const [msg, setMsg] = useState(null);
  const [alarm, setAlarm] = useState(alarmEnabled);
  const toggleAlarm = () => {
    setAlarmEnabled(!alarm);
    setAlarm(!alarm);
    if (!alarm) playAlarm("high", 1); // short test beep, and unlocks sound in the browser
  };

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
    <header className="header">
      <div className="brand">
        <img src="/shield.svg" alt="" className="brand-icon" />
        <div>
          <h1>CyberShield SatCom 3D</h1>
          <p className="subtitle">4D Digital Twin · Satellite–5G IoT Security</p>
        </div>
      </div>
      <div className="header-right">
        <div className={`pill ${connected ? "pill-ok" : "pill-bad"}`}>
          <span className="dot" />
          {connected ? "Live link to backend" : "Backend offline"}
          {connected && latencyMs !== null && <span className="pill-meta">{latencyMs} ms</span>}
        </div>
        <button className={`btn btn-small alarm-btn ${alarm ? "alarm-on" : ""}`} onClick={toggleAlarm}
                title="Siren in this browser when an attack is detected">
          {alarm ? "Alarm on" : "Alarm off"}
        </button>
        {user && user.company_name && (
          <div className="pill company-pill" title="You see only this company's devices">{user.company_name}</div>
        )}
        {user && authEnabled && !user.company_name && (
          <div className="pill company-pill" title="Platform (provider): you see every company">Platform</div>
        )}
        {user && (
          <div className="account">
            <button className="btn btn-small account-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
              {user.username} <span className={`role-badge role-${user.role}`}>{user.role}</span>
            </button>
            {open && (
              <div className="account-menu panel">
                <div className="small"><b>{user.username}</b> · {user.role} ({ROLE_HINT[user.role]})</div>
                <div className="small muted">{user.company_name ? `Company: ${user.company_name}` : "Platform user: sees every company"}</div>
                {authEnabled ? (
                  <>
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
                  </>
                ) : (
                  <div className="muted small">Login is switched off (AUTH_ENABLED=false).</div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
