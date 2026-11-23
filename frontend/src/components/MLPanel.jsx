import { useAuth } from "../auth.jsx";
import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api.js";

// Optional machine-learning anomaly detector (LocalOutlierFactor), next to the rules.
export default function MLPanel() {
  const { has, isPlatform } = useAuth();
  const [status, setStatus] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.mlStatus().then(setStatus).catch(() => {}), []);
  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const act = (promise, okText) => {
    setBusy(true);
    promise
      .then((r) => {
        setMessage(r.trained === false ? r.reason : okText);
        load();
      })
      .catch((e) => setMessage(e.message))
      .finally(() => setBusy(false));
  };

  if (!status) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>ML anomaly detector</h2>
        {status.installed && (
          <label className="switch small">
            <input type="checkbox" className="switch-ok" checked={status.enabled} disabled={busy || !has("respond") || !isPlatform}
                   onChange={(e) => act(api.setMl(e.target.checked), e.target.checked ? "ML detector on" : "ML detector off")} />
            Enabled
          </label>
        )}
      </div>
      {!status.installed ? (
        <p className="muted small">
          Not installed (needs <code>requirements-ml.txt</code>).
        </p>
      ) : (
        <>
          <div className="fo-stats">
            <div><span className="fo-num">{status.trained ? "yes" : "no"}</span><span className="muted small">trained</span></div>
            <div><span className="fo-num">{status.training_samples}</span><span className="muted small">training readings</span></div>
            <div><span className="fo-num">{status.readings_checked}</span><span className="muted small">checked</span></div>
            <div><span className={`fo-num ${status.readings_flagged ? "tone-warn" : ""}`}>{status.readings_flagged}</span><span className="muted small">flagged</span></div>
          </div>
          <div className="button-row">
            <button className="btn btn-small need-operator need-platform" disabled={busy} onClick={() => act(api.mlTrain(), "Model trained on the stored normal readings")}>
              {status.trained ? "Retrain" : "Train now"}
            </button>
          </div>
          {!status.trained && (
            <p className="muted small">Needs {status.min_training_readings} normal readings (about 2 minutes of simulation).</p>
          )}
        </>
      )}
      {message && <div className="small muted">{message}</div>}
    </section>
  );
}
