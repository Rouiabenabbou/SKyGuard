import { useState } from "react";
import { api } from "../services/api.js";

// Start / Pause / Reset buttons. The backend broadcasts the new state over
// the WebSocket, so the page updates even if another browser pressed the button.
export default function SimulationControls({ simulation, mqtt }) {
  const [busy, setBusy] = useState(false);
  const running = simulation?.running;

  async function run(action) {
    setBusy(true);
    try {
      await action();
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel controls">
      <div>
        <h2>Simulation</h2>
        <p className="muted small">
          {simulation
            ? `${running ? "Running" : "Paused"} · session #${simulation.session_id ?? "–"} · one reading per device every ${simulation.interval_seconds}s`
            : "Loading…"}
        </p>
        <p className="data-path small">
          <span className="path-node">Built-in simulator</span>
          <span className="path-arrow">→</span>
          {mqtt?.connected ? (
            <>
              <span className="path-node path-mqtt">MQTT broker</span>
              <span className="path-arrow">→</span>
            </>
          ) : (
            <span className="path-skip">(broker offline, sending direct)</span>
          )}
          <span className="path-node">Backend</span>
          <span className="path-arrow">→</span>
          <span className="path-node">SQLite + Dashboard</span>
        </p>
      </div>
      <div className="button-row">
        <button className="btn btn-primary need-operator need-platform" disabled={busy || running} onClick={() => run(api.startSimulation)}>
          ▶ Start
        </button>
        <button className="btn need-operator need-platform" disabled={busy || !running} onClick={() => run(api.pauseSimulation)}>
          ❚❚ Pause
        </button>
        <button className="btn btn-danger need-admin need-platform" disabled={busy} onClick={() => run(api.resetSimulation)}>
          ↺ Reset
        </button>
      </div>
    </section>
  );
}
