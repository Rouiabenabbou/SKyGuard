import { useEffect, useState } from "react";
import Sidebar from "./components/shell/Sidebar.jsx";
import Topbar from "./components/shell/Topbar.jsx";
import { pageFromHash } from "./components/shell/navigation.js";
import SimulationControls from "./components/SimulationControls.jsx";
import EventLog from "./components/EventLog.jsx";
import NetworkPanel from "./components/NetworkPanel.jsx";
import AttackPanel from "./components/AttackPanel.jsx";
import Toasts from "./components/Toasts.jsx";
import QuarantinePanel from "./components/QuarantinePanel.jsx";
import TwinPanel from "./components/TwinPanel.jsx";
import TimelinePanel from "./components/TimelinePanel.jsx";
import ReportPanel from "./components/ReportPanel.jsx";
import MLPanel from "./components/MLPanel.jsx";
import OperatorConsole from "./components/OperatorConsole.jsx";
import RealMap from "./components/RealMap.jsx";
import UsersPanel from "./components/UsersPanel.jsx";
import CompaniesPanel from "./components/CompaniesPanel.jsx";
import AnalyticsPanel from "./components/AnalyticsPanel.jsx";
import PhoneAlarmPanel from "./components/PhoneAlarmPanel.jsx";
import AuditPanel from "./components/AuditPanel.jsx";
import TelemetryTable from "./components/TelemetryTable.jsx";
import NetworkInvestigation from "./components/NetworkInvestigation.jsx";
import { useAuth } from "./auth.jsx";
import TelemetryChart from "./components/charts/TelemetryChart.jsx";
import AvailabilityChart from "./components/charts/AvailabilityChart.jsx";
import AlertCharts from "./components/charts/AlertCharts.jsx";
import { useLiveData } from "./hooks/useLiveData.js";
import { useNow } from "./hooks/useNow.js";
import { useTimeline } from "./hooks/useTimeline.js";
import { useSummary } from "./hooks/useSummary.js";
import { frameToDevices, frameToNetwork } from "./services/timeline.js";
import DeviceViewer from "./components/DeviceViewer.jsx";
import IncidentManagement from "./pages/IncidentManagement.jsx";
import ThreatHunting from "./pages/ThreatHunting.jsx";
import ThreatIntel from "./pages/ThreatIntel.jsx";
import AiAnalyst from "./pages/AiAnalyst.jsx";
import Approvals from "./pages/Approvals.jsx";
import DemoScenario from "./pages/DemoScenario.jsx";
import PlaybooksPanel from "./components/PlaybooksPanel.jsx";
import { api } from "./services/api.js";
import EngineeringPanel from "./components/EngineeringPanel.jsx";
import AiSettingsPanel from "./components/AiSettingsPanel.jsx";
import SocOverview from "./pages/SocOverview.jsx";
import AlertCenter from "./pages/AlertCenter.jsx";
import DetectionRules from "./pages/DetectionRules.jsx";
import IotAssets from "./pages/IotAssets.jsx";
import SatcomSecurity from "./pages/SatcomSecurity.jsx";
import HuaweiLab from "./pages/HuaweiLab.jsx";

const VERSION = "2.5";

function subFromHash() {
  return decodeURIComponent(window.location.hash.replace("#", "").split("?")[0].split("/")[1] ?? "") || null;
}

export default function App() {
  const {
    devices, history, readings, events, simulation, mqtt, network, alerts, toasts, dismissToast,
    quarantine, autoQuarantine, setAutoQuarantine, failover, availability, error, connected, latencyMs,
  } = useLiveData();
  const now = useNow();
  const tl = useTimeline();
  const [page, setPage] = useState(pageFromHash);
  const [sub, setSub] = useState(subFromHash);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [pwBannerHidden, setPwBannerHidden] = useState(false);
  const { can, has, defaultPasswords, authEnabled, isPlatform, user } = useAuth();
  const [pendingApprovals, setPendingApprovals] = useState(0);
  useEffect(() => {  // v2.1: pending containment approvals, shown in the sidebar
    if (!user) return undefined;
    const load = () => api.approvals("pending").then((r) => setPendingApprovals(r.pending)).catch(() => {});
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [user]);
  const summary = useSummary(page === "analytics", alerts.length);

  useEffect(() => {
    const onHash = () => {
      setPage(pageFromHash());
      setSub(subFromHash());
      setMobileOpen(false);
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const navigate = (target) => {
    if (window.location.hash === `#${target}`) return;
    window.location.hash = target;
  };
  const toggleMenu = () => (window.innerWidth <= 900 ? setMobileOpen((o) => !o) : setCollapsed((c) => !c));

  // In replay mode the 3D twin shows a recorded moment instead of the live state.
  const twinNetwork = tl.frame ? frameToNetwork(tl.frame, network) : network;
  const twinDevices = tl.frame ? frameToDevices(tl.frame, devices) : devices;
  const openAlerts = alerts.filter((a) => a.status === "open");
  const urgent = openAlerts.filter((a) => a.severity === "high" || a.severity === "critical").length;

  const counts = {
    alerts: openAlerts.length ? { value: openAlerts.length, tone: urgent ? "bad" : "" } : null,
    twin: tl.replay ? { value: "replay" } : null,
    approvals: pendingApprovals ? { value: pendingApprovals, tone: "bad" } : null,
    devices: Object.values(devices).some((d) => d.security_status === "quarantined")
      ? { value: Object.values(devices).filter((d) => d.security_status === "quarantined").length, tone: "bad" } : null,
  };

  return (
    <div className={`shell ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`}>
      {mobileOpen && <div className="sb-backdrop" onClick={() => setMobileOpen(false)} />}
      <Sidebar active={page} onNavigate={navigate} counts={counts} can={can} has={has} version={VERSION} />
      <div className="main">
        <Topbar page={page} connected={connected} latencyMs={latencyMs} devices={devices} network={network}
                alerts={alerts} onNavigate={navigate} onMenu={toggleMenu} />
        <Toasts toasts={toasts} onDismiss={dismissToast} />
        <DeviceViewer network={network} devices={devices} />

        <main className="content">
          {authEnabled && defaultPasswords && can("admin") && !pwBannerHidden && (
            <div className="default-pw-banner">
              <span>Some accounts still use their first-start password (<b>User Management</b>).</span>
              <button className="banner-close" aria-label="Hide" onClick={() => setPwBannerHidden(true)}>✕</button>
            </div>
          )}
          {(error || !connected) && (
            <div className="banner-error">
              Cannot reach the backend{error ? ` (${error})` : ""}. Is <code>uvicorn</code> running on port 8000?
            </div>
          )}

          {page === "overview" && <SocOverview events={events} availability={availability} onNavigate={navigate} />}

          {page === "alerts" && <AlertCenter key={sub ?? "list"} subId={sub ? Number(sub) : null} onNavigate={navigate} devices={devices} alerts={alerts} />}

          {page === "incidents" && <IncidentManagement key={sub ?? "list"} alerts={alerts} initialId={sub ? Number(sub) : null} />}

          {page === "approvals" && <Approvals />}

          {page === "demo" && <DemoScenario />}

          {page === "hunting" && <ThreatHunting />}

          {page === "intel" && <ThreatIntel />}

          {page === "simulation" && (
            <>
              <SimulationControls simulation={simulation} mqtt={mqtt} />
              <div className="grid-2">
                <AttackPanel devices={Object.values(devices).sort((a, b) => a.device_id.localeCompare(b.device_id))} />
                <EventLog events={events.filter((e) => e.category === "security").slice(0, 12)} />
              </div>
            </>
          )}

          {page === "network" && (
            <>
              <div className="grid-main-side">
                <NetworkPanel network={network} />
                <section className="panel"><AvailabilityChart points={availability} /></section>
              </div>
              <div className="grid-2">
                <section className="panel"><TelemetryChart history={history} metric="temperature" /></section>
                <section className="panel"><TelemetryChart history={history} metric="humidity" /></section>
              </div>
              <EventLog events={events.filter((e) => e.category === "network").slice(0, 12)} />
            </>
          )}

          {page === "satcom" && <SatcomSecurity network={network} failover={failover} />}

          {page === "devices" && (
            <IotAssets devices={devices} history={history} network={network} alerts={alerts} quarantine={quarantine}
                       now={now} subId={sub} onNavigate={navigate} />
          )}

          {page === "topology" && (
            <>
              <NetworkInvestigation />
              <RealMap network={network} devices={devices} />
            </>
          )}

          {page === "twin" && (
            <TwinPanel network={twinNetwork} devices={twinDevices} alerts={alerts} replay={tl.replay} title="3D digital twin">
              <TimelinePanel tl={tl} />
            </TwinPanel>
          )}

          {page === "rules" && <DetectionRules onNavigate={navigate} />}

          {page === "ai" && <AiAnalyst alerts={alerts} />}

          {page === "automation" && (
            <>
              <PlaybooksPanel />
              <div className="grid-2">
                <QuarantinePanel quarantine={quarantine} autoQuarantine={autoQuarantine} setAutoQuarantine={setAutoQuarantine} />
                <MLPanel />
              </div>
            </>
          )}

          {page === "analytics" && (
            <>
              <AnalyticsPanel devices={devices} />
              <section className="panel">
                <div className="panel-head"><h2>Alert statistics</h2></div>
                <AlertCharts summary={summary} />
              </section>
              <ReportPanel summary={summary} />
              <div className="grid-2">
                <TelemetryTable readings={readings} />
                <EventLog events={events} />
              </div>
            </>
          )}

          {page === "health" && <>{isPlatform && <HuaweiLab />}<EngineeringPanel /></>}

          {page === "users" && can("admin") && (
            <>
              {authEnabled && isPlatform && <CompaniesPanel />}
              <UsersPanel />
            </>
          )}

          {page === "admin" && can("admin") && (
            <>
              {isPlatform && <PhoneAlarmPanel />}
              {isPlatform && <AiSettingsPanel />}
              {!isPlatform && <section className="panel"><div className="muted">Platform settings are managed by the provider.</div></section>}
            </>
          )}

          {page === "audit" && can("admin") && <AuditPanel />}

          {page === "console" && <OperatorConsole />}

          {["users", "admin", "audit"].includes(page) && !can("admin") && (
            <section className="panel"><div className="muted">This module needs the admin role.</div></section>
          )}

          <footer className="footer muted small">
            CyberShield SecOps v{VERSION} · on Huawei Cloud · events are labelled SIM (simulator) or LAB (real test board) · API docs at{" "}
            <a href="/docs" target="_blank" rel="noreferrer">/docs</a>
          </footer>
        </main>
      </div>
    </div>
  );
}
