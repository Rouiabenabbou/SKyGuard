import { clock } from "../services/timeline.js";

const SPEEDS = [1, 2, 5, 10, 30];
const RANGES = [
  { label: "Last 10 min", minutes: 10 },
  { label: "Last 30 min", minutes: 30 },
  { label: "Last 2 h", minutes: 120 },
  { label: "Everything", minutes: 0 },
];
const CAT_CLASS = { security: "mk-security", network: "mk-network", device: "mk-device", system: "mk-system" };

// The 4D timeline: time is the fourth dimension of the digital twin.
// Live mode follows the backend; replay mode shows any recorded moment in the 3D scene.
export default function TimelinePanel({ tl }) {
  const { replay, data, cursor, frame } = tl;
  const span = data ? Math.max(1, data.end_ms - data.start_ms) : 1;
  const pct = (t) => `${(((t - data.start_ms) / span) * 100).toFixed(2)}%`;
  const recent = replay && data ? data.events.filter((e) => e.t <= cursor + 999).slice(-5).reverse() : [];

  return (
    <div className="timeline">
      <div className="timeline-bar">
        <div className="seg">
          <button className={`btn btn-small ${!replay ? "btn-primary" : ""}`} onClick={tl.exitReplay}>
            ● Live
          </button>
          <button className={`btn btn-small ${replay ? "btn-primary" : ""}`} disabled={tl.loading} onClick={replay ? tl.reload : tl.enterReplay}>
            {tl.loading ? "Loading…" : replay ? "⟳ Reload" : "⏪ Replay"}
          </button>
        </div>
        <select className="select select-small" value={tl.minutes} onChange={(e) => tl.changeRange(Number(e.target.value))} aria-label="Time range">
          {RANGES.map((r) => (
            <option key={r.minutes} value={r.minutes}>{r.label}</option>
          ))}
        </select>
        {replay && (
          <>
            <div className="seg">
              <button className="btn btn-small" title="Previous event" onClick={() => tl.jump(-1)}>⏮</button>
              <button className="btn btn-small btn-play" onClick={() => tl.setPlaying(!tl.playing)}>
                {tl.playing ? "⏸ Pause" : "▶ Play"}
              </button>
              <button className="btn btn-small" title="Next event" onClick={() => tl.jump(1)}>⏭</button>
            </div>
            <select className="select select-small" value={tl.speed} onChange={(e) => tl.setSpeed(Number(e.target.value))} aria-label="Speed">
              {SPEEDS.map((s) => (
                <option key={s} value={s}>{s}× speed</option>
              ))}
            </select>
            <span className="timeline-clock">
              {clock(cursor)}
              <span className="muted small"> · {Math.round((data.end_ms - cursor) / 1000)} s before the last frame</span>
            </span>
          </>
        )}
      </div>

      {tl.error && <div className="tone-warn small">{tl.error}</div>}

      {replay && data && (
        <>
          <div className="timeline-track">
            <div className="timeline-markers">
              {tl.keyEvents.map((e) => (
                <button
                  key={e.id}
                  className={`mk ${CAT_CLASS[e.category] ?? "mk-system"}`}
                  style={{ left: pct(Math.min(Math.max(e.t, data.start_ms), data.end_ms)) }}
                  title={`${clock(e.t)} ${e.description}`}
                  onClick={() => tl.setCursor(Math.min(e.t + 999, data.end_ms))}
                />
              ))}
            </div>
            <input
              type="range"
              className="timeline-range"
              min={data.start_ms}
              max={data.end_ms}
              step={100}
              value={cursor}
              onChange={(e) => tl.setCursor(Number(e.target.value))}
              aria-label="Timeline position"
            />
            <div className="timeline-ends muted small">
              <span>{clock(data.start_ms)}</span>
              <span>{data.count} frames</span>
              <span>{clock(data.end_ms)}</span>
            </div>
          </div>

          <div className="timeline-moment">
            {frame && (
              <div className="moment-stats small">
                <span>Availability <b>{frame.avail}%</b></span>
                <span>Open alerts <b className={frame.alerts ? "tone-bad" : ""}>{frame.alerts}</b></span>
                <span>
                  Quarantined <b>{Object.values(frame.devices).filter((d) => d.sec === "quarantined").length}</b>
                </span>
                <span>
                  On backup 5G <b>{Object.values(frame.routes).filter((r) => r.m === "backup").length}</b>
                </span>
              </div>
            )}
            <ul className="moment-events">
              {recent.length === 0 && <li className="muted small">No events yet at this moment.</li>}
              {recent.map((e) => (
                <li key={e.id} className={`small ev-${e.category}`}>
                  <span className="muted">{clock(e.t)}</span> {e.description}
                </li>
              ))}
            </ul>
          </div>
          <div className="legend-inline muted small">
            <span><i className="mk-dot mk-security" /> security</span>
            <span><i className="mk-dot mk-network" /> network / failover</span>
            <span><i className="mk-dot mk-device" /> device</span>
            <span><i className="mk-dot mk-system" /> system</span>
          </div>
        </>
      )}
    </div>
  );
}
