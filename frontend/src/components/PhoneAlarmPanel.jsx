import { useEffect, useState } from "react";
import { api } from "../services/api.js";

const SEVERITY_TEXT = {
  medium: "every attack (medium and above)",
  high: "high and critical only",
  critical: "critical only",
  low: "everything, also minor alerts",
};
const randomTopic = () => `cybershield-${Math.random().toString(36).slice(2, 8)}${Math.random().toString(36).slice(2, 8)}`;

// Platform admin: the backend rings the operator's phone by itself when an attack is detected
// (network faults such as a link going down don't ring). "Send test alarm" only checks the phone.
export default function PhoneAlarmPanel() {
  const [s, setS] = useState(null);
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.notifySettings().then(setS).catch((e) => setMsg({ ok: false, text: e.message }));
  }, []);

  if (!s) return <section className="panel"><h2>Phone alarm</h2>{msg && <div className="small tone-bad">{msg.text}</div>}</section>;
  const set = (k) => (e) => setS({ ...s, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function save(e) {
    e?.preventDefault();
    setBusy(true);
    try {
      const body = { enabled: s.enabled, ntfy_server: s.ntfy_server, ntfy_topic: s.ntfy_topic.trim(),
        min_severity: s.min_severity, telegram_chat_id: s.telegram_chat_id };
      if (token) body.telegram_token = token.trim();
      setS(await api.saveNotify(body));
      setToken("");
      setMsg({ ok: true, text: "Saved." });
      return true;
    } catch (err) {
      setMsg({ ok: false, text: err.message });
      return false;
    } finally {
      setBusy(false);
    }
  }

  // The switch saves at once, so the alarm really is on (or off) without pressing Save.
  async function toggle(e) {
    const enabled = e.target.checked;
    if (enabled && !s.ntfy_topic.trim() && !s.telegram_token_set) {
      setMsg({ ok: false, text: "Enter an ntfy topic first (or press Make a secret topic)." });
      return;
    }
    setBusy(true);
    try {
      setS(await api.saveNotify({ enabled, ntfy_topic: s.ntfy_topic.trim() }));
      setMsg({ ok: true, text: enabled ? "Automatic alarm switched on." : "Automatic alarm switched off." });
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    if (!(await save())) return;
    setBusy(true);
    try {
      const r = await api.testNotify();
      setMsg(r.ok ? { ok: true, text: "Test alarm sent. Your phone should ring now. From now on every attack rings it automatically." }
        : { ok: false, text: r.results.map((x) => `${x.channel}: ${x.ok ? "ok" : x.error}`).join(" · ") });
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
      api.notifySettings().then(setS).catch(() => {});
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Phone alarm</h2>
        <label className="switch small">
          <input type="checkbox" className="switch-ok" checked={s.enabled} onChange={toggle} disabled={busy} /> Automatic alarm
        </label>
      </div>
      <div className={`alarm-state ${s.enabled ? "on" : "off"}`}>
        <span className="alarm-dot" />
        {s.enabled
          ? <span><b>Automatic alarm is on.</b> Your phone rings by itself for {SEVERITY_TEXT[s.min_severity]}.</span>
          : <span><b>Automatic alarm is off.</b> Attacks will not ring your phone.</span>}
      </div>
      <form className="config-form" onSubmit={save}>
        <div className="builder-row three">
          <label><span>ntfy topic (secret, like a password)</span>
            <input value={s.ntfy_topic} onChange={set("ntfy_topic")} pattern="[A-Za-z0-9_-]*" maxLength={64} placeholder="cybershield-xxxxxxxxxxxx" />
          </label>
          <label><span>Ring for</span>
            <select value={s.min_severity} onChange={set("min_severity")}>
              {Object.entries(SEVERITY_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label><span>ntfy server</span><input value={s.ntfy_server} onChange={set("ntfy_server")} /></label>
        </div>
        <div className="config-actions" style={{ justifyContent: "flex-start" }}>
          <button type="button" className="btn btn-small" onClick={() => setS({ ...s, ntfy_topic: randomTopic() })}>Make a secret topic</button>
        </div>
        <details className="small">
          <summary>Telegram too (optional)</summary>
          <div className="builder-row">
            <label><span>Bot token {s.telegram_token_set && <span className="tone-ok">(set)</span>}</span>
              <input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={s.telegram_token_set ? "leave empty to keep" : "from @BotFather"} /></label>
            <label><span>Chat ID</span><input value={s.telegram_chat_id} onChange={set("telegram_chat_id")} placeholder="from @userinfobot" /></label>
          </div>
        </details>
        <div className="config-actions">
          <button className="btn btn-small" disabled={busy}>Save</button>
          <button type="button" className="btn btn-small btn-primary" disabled={busy} onClick={test}>Send test alarm</button>
        </div>
      </form>
      <div className="small muted">Sent {s.stats?.sent ?? 0} · failed {s.stats?.failed ?? 0}{s.stats?.last_error ? ` · last error: ${s.stats.last_error}` : ""}</div>
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </section>
  );
}
