export const TABS = [
  { id: "overview", label: "Overview" },
  { id: "twin", label: "4D Twin" },
  { id: "network", label: "Network" },
  { id: "security", label: "Security" },
  { id: "incidents", label: "Incidents" },
  { id: "engineering", label: "Engineering" },
  { id: "map", label: "Real map" },
  { id: "data", label: "Data & Reports" },
  { id: "analytics", label: "Analytics" },
  { id: "ai", label: "AI assistant" },
  { id: "console", label: "Console" },
  { id: "admin", label: "Admin", role: "admin" },
];

// Top navigation. The chosen tab is kept in the address bar (#network...), so a refresh keeps it.
export default function Tabs({ active, onChange, badges = {}, can = () => true }) {
  return (
    <nav className="tabs" role="tablist">
      {TABS.filter((t) => !t.role || can(t.role)).map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          className={`tab ${active === t.id ? "tab-active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {badges[t.id] ? <span className="tab-badge">{badges[t.id]}</span> : null}
        </button>
      ))}
    </nav>
  );
}
