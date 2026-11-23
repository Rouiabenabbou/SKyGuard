import { alertLabel } from "./AlertsPanel.jsx";

// Pop-up notifications for new high and critical alerts.
export default function Toasts({ toasts, onDismiss }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast sev-border-${t.severity}`} onClick={() => onDismiss(t.id)}>
          <div className="alert-top">
            <span className={`sev sev-${t.severity}`}>{t.severity}</span>
            <strong>{alertLabel(t.alert_type)}</strong>
          </div>
          <div className="small">{t.description}</div>
        </div>
      ))}
    </div>
  );
}
