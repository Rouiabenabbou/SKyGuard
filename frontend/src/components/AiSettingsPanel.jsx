import { useEffect, useState } from "react";
import { api } from "../services/api.js";

// v2.6: the AI analyst runs on DeepSeek (api.deepseek.com).
const PROVIDERS = {
  deepseek: { name: "DeepSeek", url: "https://platform.deepseek.com/api_keys", local: false, needsKey: true },
};

// Platform admin: paste the DeepSeek API key here instead of editing backend/.env.
// The key is stored in the database and never shown again (only its last 4 characters).
export default function AiSettingsPanel() {
  const [s, setS] = useState(null);
  const [provider, setProvider] = useState("deepseek");
  const [key, setKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.aiSettings().then((r) => {
      setS(r);
      setProvider(PROVIDERS[r.saved_provider] ? r.saved_provider : "deepseek");
      setBaseUrl(r.saved_base_url || "");
      setModel(r.saved_model || "");
    }).catch((e) => setMsg({ ok: false, text: e.message }));
  }, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.saveAiSettings({ provider, api_key: key.trim() || undefined, model: model.trim(),
        base_url: PROVIDERS[provider].local ? baseUrl.trim() : undefined });
      setS(r);
      setKey("");
      const t = await api.testAi();
      setS((old) => ({ ...old, ...t }));
      setMsg(t.ok ? { ok: true, text: `Working: ${t.provider} answered "${t.answer}".` } : { ok: false, text: `Saved, but the test failed: ${t.error}` });
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      setS(await api.saveAiSettings({ provider: "deepseek", api_key: "", model: "" }));
      setProvider("deepseek");
      setMsg({ ok: true, text: "AI turned off. The offline analyst answers now." });
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  if (!s) return <section className="panel"><h2>AI assistant</h2>{msg && <div className="small tone-bad">{msg.text}</div>}</section>;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>AI assistant</h2>
        <span className={`status-chip`} style={{ "--chip": s.configured ? "#16a34a" : "#64748b" }}>
          {s.configured ? `${s.provider_name || s.provider} · ${s.model}` : "offline analyst"}
        </span>
      </div>
      <form className="config-form" onSubmit={save}>
        <div className="builder-row three">
          <label><span>Provider</span>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {Object.entries(PROVIDERS).map(([k, p]) => <option key={k} value={k}>{p.name}</option>)}
            </select>
          </label>
          {PROVIDERS[provider].local && (
            <label><span>API address</span>
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api-ap-southeast-1.modelarts-maas.com/v1" />
            </label>
          )}
          <label><span>Model</span>
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="deepseek-chat (default) or deepseek-reasoner" />
          </label>
          <label><span>API key {PROVIDERS[provider].local && !PROVIDERS[provider].needsKey && <span className="muted">(optional)</span>} {s.key_saved && <span className="tone-ok">(saved {s.key_hint})</span>}{s.key_from === ".env" && <span className="muted"> (from .env)</span>}</span>
            <input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off"
                   placeholder={s.key_saved ? "leave empty to keep the saved key" : "paste your DeepSeek API key (sk-...)"} />
          </label>
          <label><span>Get a key</span>
            <a className="btn btn-small" href={PROVIDERS[provider].url} target="_blank" rel="noreferrer">Open {PROVIDERS[provider].name.split(" (")[0]} ↗</a>
          </label>
        </div>
        <div className="config-actions">
          {s.configured && s.key_from === "dashboard" && <button type="button" className="btn btn-small" disabled={busy} onClick={remove}>Turn off</button>}
          <button className="btn btn-small btn-primary" disabled={busy || (!key && !s.key_saved && (PROVIDERS[provider].needsKey || !PROVIDERS[provider].local))}>{busy ? "Testing…" : "Save and test"}</button>
        </div>
      </form>
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </section>
  );
}
