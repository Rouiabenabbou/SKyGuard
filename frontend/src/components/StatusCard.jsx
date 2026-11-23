// A small card showing one value. `tone` colours the value: ok, warn, bad, or neutral.
export default function StatusCard({ label, value, hint, tone = "neutral" }) {
  return (
    <div className="card">
      <div className="card-label">{label}</div>
      <div className={`card-value tone-${tone}`}>{value}</div>
      {hint && <div className="card-hint">{hint}</div>}
    </div>
  );
}
