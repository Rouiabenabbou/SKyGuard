// Everything that happened, newest first. In Phase 9 this becomes the 4D timeline.
const CATEGORY_ICON = { system: "⚙️", device: "📡", security: "🛡️", network: "🛰" };

export default function EventLog({ events }) {
  return (
    <section className="panel">
      <h2>Event log</h2>
      {events.length === 0 ? (
        <p className="muted">No events yet.</p>
      ) : (
        <ul className="event-list">
          {events.map((e) => (
            <li key={e.id}>
              <span className="event-time">{new Date(e.timestamp).toLocaleTimeString()}</span>
              <span>{CATEGORY_ICON[e.category] ?? "•"}</span>
              <span>{e.description}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
