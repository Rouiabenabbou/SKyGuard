// All HTTP calls to the backend live here, so components never build URLs
// themselves. The Vite proxy forwards "/api/..." to http://127.0.0.1:8000.

// v1.1: the login token is kept in localStorage and sent with every call.
const TOKEN_KEY = "cybershield.token";
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private window: the login lasts until the page is closed */
  }
}
// The app listens for this event and shows the login screen again.
export const LOGGED_OUT_EVENT = "cybershield:logged-out";

async function request(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers ?? {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && !path.startsWith("/api/auth/login")) {
    setToken(null);
    window.dispatchEvent(new Event(LOGGED_OUT_EVENT));
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = Array.isArray(body.detail)
        ? body.detail
            .map((d) => {
              const field = d.loc?.length > 1 ? `${d.loc.at(-1)}: ` : "";
              return field + d.msg.replace(/^Value error, /, "");
            })
            .join("; ")
        : body.detail ?? "";
    } catch {
      /* not JSON */
    }
    throw new Error(detail || `${path} failed with HTTP ${response.status}`);
  }
  return response.json();
}

const post = (path, body) =>
  request(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

const put = (path, body) =>
  request(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const del = (path) => request(path, { method: "DELETE" });

const qs = (params = {}) => new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString();

// v2.1: download a file from an endpoint that needs the login token (exports, reports).
async function download(path, filename) {
  const token = getToken();
  const r = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!r.ok) throw new Error(`${path} failed with HTTP ${r.status}`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob());
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export const api = {
  // login and users (v1.1)
  authConfig: () => request("/api/auth/config"),
  login: (username, password, code) => post("/api/auth/login", { username, password, ...(code ? { code } : {}) }),
  logout: () => post("/api/auth/logout"),
  me: () => request("/api/auth/me"),
  changePassword: (old_password, new_password) => post("/api/auth/password", { old_password, new_password }),
  users: () => request("/api/auth/users"),
  createUser: (user) => post("/api/auth/users", user),
  updateUser: (name, changes) => put(`/api/auth/users/${encodeURIComponent(name)}`, changes),
  deleteUser: (name) => del(`/api/auth/users/${encodeURIComponent(name)}`),
  audit: (limit = 200) => request(`/api/audit?limit=${limit}`),
  // many companies (v1.2, platform admin)
  companies: () => request("/api/companies"),
  createCompany: (company) => post("/api/companies", company),
  updateCompany: (id, changes) => put(`/api/companies/${encodeURIComponent(id)}`, changes),
  deleteCompany: (id) => del(`/api/companies/${encodeURIComponent(id)}`),
  // long-term data and analytics (v1.3)
  analyticsSummary: () => request("/api/analytics/summary"),
  analyticsTrends: (days, bucket = "day") => request(`/api/analytics/trends?days=${days}&bucket=${bucket}`),
  analyticsAlerts: (days) => request(`/api/analytics/alerts?days=${days}`),
  analyticsForecast: (deviceId, hours = 24) => request(`/api/analytics/forecast?device_id=${encodeURIComponent(deviceId)}&hours=${hours}`),
  generateHistory: (days, interval_minutes) => post("/api/analytics/history", { days, interval_minutes }),
  historyStatus: () => request("/api/analytics/history"),
  deleteHistory: () => del("/api/analytics/history"),
  rollupNow: () => post("/api/analytics/rollup"),
  // phone alarm (v1.2, platform admin)
  notifySettings: () => request("/api/notify/settings"),
  // v1.4: engineer tools, incidents, AI key from the dashboard
  engineeringDevices: () => request("/api/engineering/devices"),
  systemInfo: () => request("/api/engineering/system"),
  firmwareList: () => request("/api/engineering/firmware"),
  setMaintenance: (id, on, reason = "") => post(`/api/devices/${id}/maintenance`, { on, reason }),
  rebootDevice: (id) => post(`/api/devices/${id}/reboot`),
  updateFirmware: (id, version) => post(`/api/devices/${id}/firmware`, { version }),
  incidents: (status) => request(`/api/incidents${status ? `?status=${status}` : ""}`),
  incident: (id) => request(`/api/incidents/${id}`),
  createIncident: (body) => post("/api/incidents", body),
  updateIncident: (id, body) => put(`/api/incidents/${id}`, body),
  addIncidentNote: (id, text) => post(`/api/incidents/${id}/notes`, { text }),
  aiSettings: () => request("/api/ai/settings"),
  saveAiSettings: (body) => put("/api/ai/settings", body),
  testAi: () => post("/api/ai/test"),
  saveNotify: (changes) => put("/api/notify/settings", changes),
  testNotify: () => post("/api/notify/test"),
  assignDevice: (deviceId, companyId) => put(`/api/companies/devices/${encodeURIComponent(deviceId)}`, { company_id: companyId || null }),
  // real location + sensors, motion (v1.1)
  setProfile: (id, profile) => put(`/api/profiles/${encodeURIComponent(id)}`, profile),
  simulateMotion: (id, night = true) => post(`/api/devices/${encodeURIComponent(id)}/motion?night=${night}`),
  // AI assistant (v1.1)
  aiStatus: () => request("/api/ai/status"),
  aiChat: (message, history) => post("/api/ai/chat", { message, history }),
  aiExplainAlert: (id) => post(`/api/ai/explain-alert/${id}`),
  aiReport: () => post("/api/ai/report"),
  // system
  health: () => request("/api/health"),
  info: () => request("/api/info"),
  mqttStatus: () => request("/api/mqtt/status"),
  // devices & data
  devices: () => request("/api/devices"),
  device: (id) => request(`/api/devices/${encodeURIComponent(id)}`),
  telemetry: (limit = 200) => request(`/api/telemetry?limit=${limit}`),
  events: (limit = 30) => request(`/api/events?limit=${limit}`),
  configureDevice: (id, config) =>
    request(`/api/devices/${encodeURIComponent(id)}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  addDevice: (device) => post("/api/devices", device),
  removeDevice: (id) => request(`/api/devices/${encodeURIComponent(id)}`, { method: "DELETE" }),
  // network builder
  addNode: (node) => post("/api/network/nodes", node),
  removeNode: (id) => request(`/api/network/nodes/${encodeURIComponent(id)}`, { method: "DELETE" }),
  addLink: (link) => post("/api/network/links", link),
  removeLink: (id) => request(`/api/network/links/${encodeURIComponent(id)}`, { method: "DELETE" }),
  // v2.0: SOC
  socOverview: () => request("/api/soc/overview"),
  socRules: () => request("/api/soc/rules"),
  setRule: (id, enabled) => put(`/api/soc/rules/${encodeURIComponent(id)}`, { enabled }),
  testRule: (id, deviceId) => post(`/api/soc/rules/${encodeURIComponent(id)}/test${deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ""}`),
  socAlerts: (params = {}) => request(`/api/soc/alerts?${new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString()}`),
  socAlert: (id) => request(`/api/soc/alerts/${id}`),
  alertAction: (id, action, extra = {}) => post(`/api/soc/alerts/${id}/action`, { action, ...extra }),
  // v2.1 stage 2: threat hunting + GNSS
  hunt: (params) => request(`/api/hunt/events?${qs(params)}`),
  huntExport: (params, format) => download(`/api/hunt/export?${qs({ ...params, format })}`, `cybershield-hunt.${format}`),
  huntQueries: () => request("/api/hunt/queries"),
  saveHuntQuery: (body) => post("/api/hunt/queries", body),
  deleteHuntQuery: (id) => del(`/api/hunt/queries/${id}`),
  gnss: () => request("/api/soc/gnss"),
  // stage 3: threat intel, AI analyst, incident workflow
  intelProviders: () => request("/api/intel/providers"),
  intelLookup: (value, external = true) => request(`/api/intel/lookup?${qs({ value, external })}`),
  iocs: (q) => request(`/api/intel/iocs?${qs({ q })}`),
  addIoc: (body) => post("/api/intel/iocs", body),
  updateIoc: (id, body) => put(`/api/intel/iocs/${id}`, body),
  deleteIoc: (id) => del(`/api/intel/iocs/${id}`),
  sightings: (value) => request(`/api/intel/sightings?${qs({ value })}`),
  aiTools: () => request("/api/ai/tools"),
  aiRunTool: (name, args) => post(`/api/ai/tools/${name}`, args),
  aiInvestigate: (body) => post("/api/ai/investigate", body),
  aiInvestigations: (params) => request(`/api/ai/investigations?${qs(params)}`),
  workflow: (id) => request(`/api/incidents/${id}/workflow`),
  setPhase: (id, phase, note) => post(`/api/incidents/${id}/phase`, { phase, note }),
  addEvidence: (id, body) => post(`/api/incidents/${id}/evidence`, body),
  setMitre: (id, techniques) => put(`/api/incidents/${id}/mitre`, { techniques }),
  incidentReport: (id) => request(`/api/incidents/${id}/report`),
  downloadReport: (id) => download(`/api/incidents/${id}/report?format=md`, `incident-${id}-report.md`),
  // stage 4: playbooks, approvals, two-factor, audit chain, demo
  playbooks: () => request("/api/playbooks"),
  startPlaybook: (id, playbook_id) => post(`/api/incidents/${id}/playbooks`, { playbook_id }),
  runStep: (id, runId, step, body = {}) => post(`/api/incidents/${id}/playbooks/${runId}/steps/${step}`, body),
  approvals: (status) => request(`/api/approvals?${qs({ status })}`),
  requestApproval: (body) => post("/api/approvals", body),
  approve: (id, note, code) => post(`/api/approvals/${id}/approve`, { note, code }),
  reject: (id, note) => post(`/api/approvals/${id}/reject`, { note }),
  roles: () => request("/api/auth/roles"),
  mfaSetup: () => post("/api/auth/mfa/setup"),
  mfaEnable: (code) => post("/api/auth/mfa/enable", { code }),
  mfaDisable: (code) => post("/api/auth/mfa/disable", { code }),
  mfaReset: (name) => del(`/api/auth/users/${encodeURIComponent(name)}/mfa`),
  auditVerify: () => request("/api/audit/verify"),
  demo: () => request("/api/soc/demo"),
  startDemo: () => post("/api/soc/demo/start"),
  // v1.5: investigation graph
  graph: (hours = 24) => request(`/api/analytics/graph?hours=${hours}`),
  graphLayout: () => request("/api/analytics/graph/layout"),
  saveGraphLayout: (positions) => put("/api/analytics/graph/layout", { positions }),
  rewireDevice: (id, access_node, backup_node) => post(`/api/network/devices/${encodeURIComponent(id)}/access`, { access_node, backup_node }),
  // simulation controls
  simulationStatus: () => request("/api/simulation/status"),
  startSimulation: () => post("/api/simulation/start"),
  pauseSimulation: () => post("/api/simulation/pause"),
  resetSimulation: () => post("/api/simulation/reset"),
  // network (Phase 4)
  networkTopology: () => request("/api/network/topology"),
  networkStatus: () => request("/api/network/status"),
  linkHistory: (id, limit = 60) => request(`/api/network/links/${encodeURIComponent(id)}/history?limit=${limit}`),
  setLinkState: (id, state) => post(`/api/network/links/${encodeURIComponent(id)}/state`, { state }),
  setNodeState: (id, state) => post(`/api/network/nodes/${encodeURIComponent(id)}/state`, { state }),
  // security (Phase 5)
  alerts: (limit = 50) => request(`/api/alerts?limit=${limit}`),
  alertStats: () => request("/api/alerts/stats"),
  resolveAlert: (id) => post(`/api/alerts/${id}/resolve`),
  // quarantine (Phase 6)
  quarantineDevice: (id, reason) => post(`/api/devices/${encodeURIComponent(id)}/quarantine`, reason ? { reason } : undefined),
  releaseDevice: (id) => post(`/api/devices/${encodeURIComponent(id)}/release`),
  quarantineList: () => request("/api/quarantine"),
  quarantineSettings: () => request("/api/quarantine/settings"),
  setAutoQuarantine: (enabled) => post("/api/quarantine/settings", { auto_quarantine: enabled }),
  // failover (Phase 8)
  failoverStatus: () => request("/api/failover/status"),
  failoverHistory: (limit = 20) => request(`/api/failover/history?limit=${limit}`),
  setFailover: (enabled) => post("/api/failover/settings", { enabled }),
  failoverDrill: (seconds) => post(`/api/failover/drill${seconds ? `?seconds=${seconds}` : ""}`),
  // 4D timeline (Phase 9)
  timelineRange: () => request("/api/timeline/range"),
  timelineFrames: (minutes, max = 900) =>
    request(`/api/timeline/frames?max=${max}${minutes ? `&minutes=${minutes}` : ""}`),
  // device commands over MQTT (Phase 11)
  deviceCommand: (id, action) => post(`/api/devices/${encodeURIComponent(id)}/command`, { action }),
  // optional ML detector (Phase 12)
  mlStatus: () => request("/api/ml/status"),
  mlTrain: () => post("/api/ml/train"),
  // v2.2 Huawei Cloud: IoTDA bridge, ModelArts model, lab test report
  iotdaStatus: () => request("/api/iotda/status"),
  aeStatus: () => request("/api/ml/autoencoder"),
  aeReload: () => post("/api/ml/autoencoder/reload"),
  labReport: (hours) => request(`/api/lab/report?hours=${hours}`),
  downloadLabReport: (hours) => download(`/api/lab/report?hours=${hours}&format=md`, "cybershield-lab-report.md"),
  setMl: (enabled) => post("/api/ml/settings", { enabled }),
  // reports (Phase 10)
  reportSummary: () => request("/api/report/summary"),
  exportUrl: (name) => `/api/export/${name}.csv${getToken() ? `?token=${encodeURIComponent(getToken())}` : ""}`,
  auditCsvUrl: () => `/api/audit/export.csv${getToken() ? `?token=${encodeURIComponent(getToken())}` : ""}`,
  saveExport: (name) => post(`/api/export/${encodeURIComponent(name)}/save`),
  attack: (name, deviceId) =>
    post(`/api/simulation/attack/${name}${deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ""}`),
};
