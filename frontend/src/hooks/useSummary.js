import { useEffect, useState } from "react";
import { api } from "../services/api.js";

// Session summary (alert statistics, totals...) refreshed every few seconds while a tab needs it.
export function useSummary(active, refreshKey) {
  const [summary, setSummary] = useState(null);
  useEffect(() => {
    if (!active) return undefined;
    const load = () => api.reportSummary().then(setSummary).catch(() => {});
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [active, refreshKey]);
  return summary;
}
