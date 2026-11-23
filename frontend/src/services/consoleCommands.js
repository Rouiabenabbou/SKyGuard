// Operator console: turns a typed command into API calls and text output.
// Every command goes through the same REST API as the buttons, so the console
// can do nothing the dashboard could not. Everything stays inside the simulation.
import { api } from "./api.js";

const ATTACKS = {
  flood: "excessive-traffic",
  unauth: "unauthorized-device",
  abnormal: "abnormal-reading",
  storm: "connection-storm",
};
const STATES = ["auto", "degraded", "offline"];

// [usage, description] shown by "help"
export const HELP = [
  ["help", "show this list"],
  ["status", "system summary (backend, simulation, MQTT, network, alerts)"],
  ["devices", "list all devices with their latest values"],
  ["device <id>", "details of one device"],
  ["config <id> temp <min> <max>", "change the allowed temperature range"],
  ["config <id> humidity <min> <max>", "change the allowed humidity range"],
  ["config <id> name|type|location <text>", "rename a device, change its type or location"],
  ["adddevice <id> satellite|5g [via <node>] [name]", "add a new IoT device (simulated)"],
  ["removedevice <id>", "remove a device you added"],
  ["addnode <id> satellite|ground|tower [name]", "network builder: add a satellite, ground station or 5G tower"],
  ["addlink <from> <to> satellite|5g|fiber|lan [backup]", "network builder: connect two nodes"],
  ["removenode <id> | removelink <link-id>", "remove a node or link you added"],
  ["nodes", "list every network node"],
  ["quarantine <id> [reason]", "logically quarantine a device (simulated)"],
  ["release <id>", "release a device / mark it safe"],
  ["autoquarantine on|off", "turn automatic quarantine on or off"],
  ["identify <id> | ping <id>", "send a harmless MQTT command to the device"],
  ["alerts [n]", "latest alerts (default 10)"],
  ["resolve <alert-id>", "mark an alert as resolved"],
  ["events [n]", "latest events (default 10)"],
  ["routes", "current network route of each device"],
  ["links", "status of every network link"],
  ["link <link-id> auto|degraded|offline", "simulate a link failure (auto = back to normal)"],
  ["node <node-id> auto|degraded|offline", "simulate a node failure, e.g. node SAT-1 offline"],
  ["failover on|off", "turn satellite → 5G failover on or off"],
  ["failover drill [seconds]", "run a satellite outage drill"],
  ["attack flood|unauth|abnormal|storm [id]", "start a simulated attack"],
  ["fix <id>", "fix one device: release it and resolve its open alerts"],
  ["fix network", "bring every link and node back to normal"],
  ["fix all", "fix every device, every alert and the whole network"],
  ["export telemetry|alerts|events|quarantine|failover|all", "save CSV files into the project's exports folder"],
  ["motion <id> [day]", "simulate movement in front of a device's motion sensor (night by default)"],
  ["sensor <id> motion on|off", "say whether a device has a PIR motion sensor"],
  ["where <id>", "show where a device or node really is (place, address, coordinates)"],
  ["ai <question>", "ask the AI security assistant about the live system"],
  ["whoami", "show your account, role and company"],
  ["sim start|pause|reset", "control the built-in simulator"],
  ["ml status|train|on|off", "optional machine-learning detector"],
  ["clear", "clear the screen"],
];

export const COMMAND_NAMES = [...new Set(HELP.flatMap(([u]) => u.split(" | ").map((p) => p.split(" ")[0])))];

class UsageError extends Error {}

const pad = (text, width) => String(text).padEnd(width);
const num = (v, unit = "") => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}${unit}`);
const time = (iso) => (iso ? new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleTimeString() : "—");

function table(rows) {
  const widths = rows[0].map((_, i) => Math.max(...rows.map((r) => String(r[i]).length)));
  return rows.map((r) => r.map((c, i) => pad(c, widths[i])).join("  ").trimEnd());
}

function needArg(value, usage) {
  if (value === undefined || value === "") throw new UsageError(`usage: ${usage}`);
  return value;
}

function toNumber(value, usage) {
  const n = Number(needArg(value, usage));
  if (Number.isNaN(n)) throw new UsageError(`"${value}" is not a number. usage: ${usage}`);
  return n;
}

function onOff(value, usage) {
  const v = needArg(value, usage).toLowerCase();
  if (v !== "on" && v !== "off") throw new UsageError(`usage: ${usage}`);
  return v === "on";
}

async function findDevice(id, usage) {
  const wanted = needArg(id, usage).toUpperCase();
  const { devices } = await api.devices();
  const device = devices.find((d) => d.device_id === wanted);
  if (!device) {
    throw new UsageError(`unknown device "${wanted}". Known: ${devices.map((d) => d.device_id).join(", ")}`);
  }
  return device;
}

const COMMANDS = {
  async help() {
    const width = Math.max(...HELP.map(([u]) => u.length));
    return ["Available commands:", ...HELP.map(([u, d]) => `  ${pad(u, width)}  ${d}`),
      "", "Tip: ↑/↓ = command history, Tab = complete the command name."];
  },

  async status() {
    const [health, sim, mqtt, net, q, fo, alerts] = await Promise.all([
      api.health(), api.simulationStatus(), api.mqttStatus(), api.networkStatus(),
      api.quarantineSettings(), api.failoverStatus(), api.alerts(200),
    ]);
    const open = alerts.alerts.filter((a) => a.status === "open");
    return [
      `backend      ${health.status} · uptime ${Math.round(health.uptime_seconds)} s`,
      `simulation   ${sim.running ? "running" : "paused"} · session #${sim.session_id} · reading every ${sim.interval_seconds} s`,
      `mqtt         ${mqtt.connected ? "connected" : mqtt.enabled === false ? "disabled" : "offline"} · ${mqtt.messages_received} in · ${mqtt.messages_rejected} rejected`,
      `network      availability ${net.availability.current}% (session ${net.availability.session}%) · links ${net.links_online} online, ${net.links_degraded} degraded, ${net.links_offline} offline`,
      `failover     ${fo.enabled ? "on" : "off"} · ${fo.stats.failovers} failovers · ${fo.stats.readings_lost} readings lost`,
      `quarantine   auto ${q.auto_quarantine ? "on" : "off"} · ${net.availability.quarantined_devices} device(s) quarantined`,
      `alerts       ${open.length} open (${open.filter((a) => a.severity === "critical" || a.severity === "high").length} high/critical) · ${alerts.count} total`,
    ];
  },

  async devices() {
    const { devices } = await api.devices();
    return table([
      ["ID", "NAME", "STATUS", "SECURITY", "TEMP", "HUM", "LINK", "ALLOWED TEMP", "ALLOWED HUM"],
      ...devices.map((d) => [
        d.device_id, d.device_name, d.status, d.security_status, num(d.temperature, "°C"), num(d.humidity, "%"),
        d.connection_type, `${d.ranges.temperature[0]}–${d.ranges.temperature[1]}°C`,
        `${d.ranges.humidity[0]}–${d.ranges.humidity[1]}%`,
      ]),
    ]);
  },

  async device([id]) {
    const d = await findDevice(id, "device <id>");
    return [
      `${d.device_id} · ${d.device_name}`,
      `  type         ${d.device_type}`,
      `  location     ${d.location || "—"}`,
      `  connection   ${d.connection_type}`,
      `  status       ${d.status} · security ${d.security_status}`,
      `  latest       ${num(d.temperature, " °C")} · ${num(d.humidity, " %")} · battery ${num(d.battery, " %")}`,
      `  allowed      ${d.ranges.temperature[0]} to ${d.ranges.temperature[1]} °C · ${d.ranges.humidity[0]} to ${d.ranges.humidity[1]} %`,
      `  messages     ${d.message_count} · last seen ${time(d.last_seen)}`,
    ];
  },

  async config([id, field, ...rest]) {
    const usage = "config <id> temp|humidity <min> <max>  or  config <id> name|type|location <text>";
    const d = await findDevice(id, usage);
    const cfg = {
      device_name: d.device_name, device_type: d.device_type, location: d.location ?? "",
      temp_min: d.ranges.temperature[0], temp_max: d.ranges.temperature[1],
      humidity_min: d.ranges.humidity[0], humidity_max: d.ranges.humidity[1],
    };
    switch ((field ?? "").toLowerCase()) {
      case "temp":
      case "temperature":
        cfg.temp_min = toNumber(rest[0], usage);
        cfg.temp_max = toNumber(rest[1], usage);
        break;
      case "humidity":
      case "hum":
        cfg.humidity_min = toNumber(rest[0], usage);
        cfg.humidity_max = toNumber(rest[1], usage);
        break;
      case "name":
        cfg.device_name = needArg(rest.join(" "), usage);
        break;
      case "type":
        cfg.device_type = needArg(rest.join(" "), usage);
        break;
      case "location":
        cfg.location = rest.join(" ");
        break;
      default:
        throw new UsageError(`usage: ${usage}`);
    }
    const res = await api.configureDevice(d.device_id, cfg);
    return res.updated ? [`✔ ${d.device_id} updated:`, ...res.changes.map((c) => `  ${c}`)] : ["nothing changed"];
  },

  async adddevice([id, conn, ...rest]) {
    const usage = "adddevice <id> satellite|5g [via <node>] [name]   e.g. adddevice IOT-004 satellite Water Tank 04";
    const deviceId = needArg(id, usage).toUpperCase();
    const connection = (conn ?? "").toLowerCase();
    if (connection !== "satellite" && connection !== "5g") throw new UsageError(`usage: ${usage}`);
    let access;
    if ((rest[0] ?? "").toLowerCase() === "via") {
      access = needArg(rest[1], usage).toUpperCase();
      rest = rest.slice(2);
    }
    const name = rest.join(" ") || `New Sensor ${deviceId}`;
    const res = await api.addDevice({
      device_id: deviceId, device_name: name, device_type: "Environmental Sensor", location: "",
      connection_type: connection, ...(access ? { access_node: access } : {}),
      temp_min: 0, temp_max: 45, humidity_min: 10, humidity_max: 90, simulated: true,
    });
    const d = res.device;
    return [`✔ ${d.device_id} (${d.device_name}) added on ${connection}${access ? ` via ${access}` : ""}. First reading in ~1 s.`,
      `  change its limits with: config ${d.device_id} temp <min> <max>`];
  },

  async removedevice([id]) {
    const deviceId = needArg(id, "removedevice <id>").toUpperCase();
    await api.removeDevice(deviceId);
    return [`✔ ${deviceId} removed (its old readings stay in the history)`];
  },

  async addnode([id, type, ...name]) {
    const usage = "addnode <id> satellite|ground|tower [name]   e.g. addnode SAT-2 satellite";
    const types = { satellite: "satellite", sat: "satellite", ground: "ground_station", gs: "ground_station",
      tower: "base_station", "5g": "base_station", bs: "base_station" };
    const nodeType = types[(type ?? "").toLowerCase()];
    if (!nodeType) throw new UsageError(`usage: ${usage}`);
    const res = await api.addNode({ node_id: needArg(id, usage).toUpperCase(), name: name.join(" "), node_type: nodeType });
    return [`✔ ${res.node.node_id} added (${res.node.name}). Connect it, e.g.: addlink ${res.node.node_id} CORE fiber`];
  },

  async addlink([a, b, type, role]) {
    const usage = "addlink <from> <to> satellite|5g|fiber|lan [backup]   e.g. addlink SAT-2 GS-2 satellite";
    const linkType = (type ?? "").toLowerCase();
    if (!["satellite", "5g", "fiber", "lan"].includes(linkType)) throw new UsageError(`usage: ${usage}`);
    const res = await api.addLink({
      source_node: needArg(a, usage).toUpperCase(), target_node: needArg(b, usage).toUpperCase(),
      link_type: linkType, role: (role ?? "").toLowerCase() === "backup" ? "backup" : "primary",
    });
    const l = res.link;
    return [`✔ ${l.link_id}: ${l.source_node} ↔ ${l.target_node} (${l.link_type}, ${l.is_active_path ? "primary" : "backup"})`];
  },

  async removenode([id]) {
    const nodeId = needArg(id, "removenode <id>").toUpperCase();
    const res = await api.removeNode(nodeId);
    return [`✔ ${nodeId} removed${res.links_removed.length ? ` with link(s) ${res.links_removed.join(", ")}` : ""}`];
  },

  async removelink([id]) {
    const linkId = needArg(id, "removelink <link-id>").toUpperCase();
    await api.removeLink(linkId);
    return [`✔ ${linkId} removed`];
  },

  async nodes() {
    const topo = await api.networkTopology();
    return table([
      ["NODE", "TYPE", "STATUS", "ADDED BY YOU", "NAME"],
      ...topo.nodes.map((n) => [n.node_id, n.node_type, n.status, n.added ? "yes" : "", n.name]),
    ]);
  },

  async quarantine([id, ...reason]) {
    const d = await findDevice(id, "quarantine <id> [reason]");
    const res = await api.quarantineDevice(d.device_id, reason.length ? reason.join(" ") : "manual, from operator console");
    return [`✔ ${d.device_id}: ${res.message ?? "quarantined"}. Its messages are now blocked inside the simulation.`];
  },

  async release([id]) {
    const d = await findDevice(id, "release <id>");
    const res = await api.releaseDevice(d.device_id);
    return [`✔ ${d.device_id}: ${res.message ?? "released"}`];
  },

  async autoquarantine([v]) {
    const enabled = onOff(v, "autoquarantine on|off");
    await api.setAutoQuarantine(enabled);
    return [`✔ automatic quarantine ${enabled ? "on" : "off"}`];
  },

  async identify([id]) {
    const d = await findDevice(id, "identify <id>");
    await api.deviceCommand(d.device_id, "identify");
    return [`✔ identify sent to ${d.device_id} over MQTT (the ESP32 LED blinks 10 times)`];
  },

  async ping([id]) {
    const d = await findDevice(id, "ping <id>");
    await api.deviceCommand(d.device_id, "ping");
    return [`✔ ping sent to ${d.device_id} over MQTT`];
  },

  async alerts([n]) {
    const limit = n ? toNumber(n, "alerts [n]") : 10;
    const { alerts } = await api.alerts(limit);
    if (!alerts.length) return ["no alerts"];
    return table([
      ["#", "TIME", "SEVERITY", "STATUS", "DEVICE", "TYPE"],
      ...alerts.map((a) => [a.id, time(a.timestamp), a.severity, a.status, a.device_id ?? "—", a.alert_type]),
    ]);
  },

  async resolve([id]) {
    const alertId = toNumber(id, "resolve <alert-id>");
    await api.resolveAlert(alertId);
    return [`✔ alert #${alertId} resolved`];
  },

  async events([n]) {
    const limit = n ? toNumber(n, "events [n]") : 10;
    const { events } = await api.events(limit);
    return events.map((e) => `${time(e.timestamp)}  ${e.description}`);
  },

  async routes() {
    const net = await api.networkStatus();
    return table([
      ["DEVICE", "MODE", "LATENCY", "PATH"],
      ...Object.entries(net.routes).map(([id, r]) => [
        id, r.quarantined ? "quarantined" : r.connected ? r.mode : "no route",
        r.connected ? `${r.latency_ms} ms` : "—", r.path?.length ? r.path.join(" → ") : "—",
      ]),
    ]);
  },

  async links() {
    const topo = await api.networkTopology();
    return table([
      ["LINK", "FROM → TO", "TYPE", "ROLE", "STATUS", "LATENCY", "LOSS"],
      ...topo.links.map((l) => [
        l.link_id, `${l.source_node} → ${l.target_node}`, l.link_type, l.role,
        l.status + (l.override ? " (forced)" : ""), `${l.latency_ms} ms`, `${l.packet_loss}%`,
      ]),
    ]);
  },

  async link([id, state]) {
    const usage = "link <link-id> auto|degraded|offline";
    const linkId = needArg(id, usage).toUpperCase();
    if (!STATES.includes((state ?? "").toLowerCase())) throw new UsageError(`usage: ${usage}`);
    await api.setLinkState(linkId, state.toLowerCase());
    return [`✔ link ${linkId} set to ${state.toLowerCase()} (simulated)`];
  },

  async node([id, state]) {
    const usage = "node <node-id> auto|degraded|offline";
    const nodeId = needArg(id, usage).toUpperCase();
    if (!STATES.includes((state ?? "").toLowerCase())) throw new UsageError(`usage: ${usage}`);
    await api.setNodeState(nodeId, state.toLowerCase());
    return [`✔ node ${nodeId} set to ${state.toLowerCase()} (simulated)`];
  },

  async failover([action, seconds]) {
    const usage = "failover on|off  or  failover drill [seconds]";
    const a = needArg(action, usage).toLowerCase();
    if (a === "drill") {
      const res = await api.failoverDrill(seconds ? toNumber(seconds, usage) : undefined);
      return [`✔ satellite outage drill: ${res.message}. Watch: routes`];
    }
    const enabled = onOff(a, usage);
    await api.setFailover(enabled);
    return [`✔ automatic failover ${enabled ? "on" : "off"}`];
  },

  async attack([name, id]) {
    const usage = "attack flood|unauth|abnormal|storm [device-id]";
    const kind = ATTACKS[(name ?? "").toLowerCase()];
    if (!kind) throw new UsageError(`usage: ${usage}`);
    const res = await api.attack(kind, id ? id.toUpperCase() : undefined);
    return [`⚠ simulated ${kind} attack started${res.device_id ? ` on ${res.device_id}` : ""}. Watch: alerts`];
  },

  async fix([target]) {
    const usage = "fix <device-id> | fix network | fix all";
    const t = needArg(target, usage).toLowerCase();
    const out = [];
    const fixNetwork = async () => {
      const topo = await api.networkTopology();
      const links = topo.links.filter((l) => l.override);
      const nodes = topo.nodes.filter((n) => n.node_type !== "iot_device" && n.status !== "online");
      await Promise.all([
        ...links.map((l) => api.setLinkState(l.link_id, "auto")),
        ...nodes.map((n) => api.setNodeState(n.node_id, "auto")),
      ]);
      out.push(links.length || nodes.length
        ? `✔ network: ${nodes.map((n) => n.node_id).concat(links.map((l) => l.link_id)).join(", ")} back to normal`
        : "✔ network: nothing to fix, every link and node is normal");
    };
    const fixDevices = async (devices) => {
      const { alerts } = await api.alerts(500);
      for (const d of devices) {
        const open = alerts.filter((a) => a.status === "open" && a.device_id === d.device_id);
        await Promise.all(open.map((a) => api.resolveAlert(a.id)));
        const wasBad = d.security_status !== "normal";
        if (wasBad) await api.releaseDevice(d.device_id);
        out.push(`✔ ${d.device_id}: ${wasBad ? `${d.security_status} → normal` : "already normal"}, ${open.length} alert(s) resolved`);
      }
      return alerts;
    };
    if (t === "network") {
      await fixNetwork();
    } else if (t === "all") {
      const { devices } = await api.devices();
      const alerts = await fixDevices(devices);
      const rest = alerts.filter((a) => a.status === "open" && !devices.some((d) => d.device_id === a.device_id));
      await Promise.all(rest.map((a) => api.resolveAlert(a.id)));
      if (rest.length) out.push(`✔ ${rest.length} other alert(s) resolved (network / unknown devices)`);
      await fixNetwork();
    } else {
      await fixDevices([await findDevice(target, usage)]);
    }
    return out;
  },

  async export([name]) {
    const names = ["telemetry", "alerts", "events", "quarantine", "failover", "all"];
    const usage = `export ${names.join("|")}`;
    const n = needArg(name, usage).toLowerCase();
    if (!names.includes(n)) throw new UsageError(`usage: ${usage}`);
    const res = await api.saveExport(n);
    return [`✔ saved in ${res.folder}`, ...res.files.map((f) => `  ${f.path.split(/[\\/]/).pop()}  (${f.rows} rows)`)];
  },

  async motion([id, when]) {
    const d = await findDevice(id, "motion <id> [day]");
    const night = (when ?? "night").toLowerCase() !== "day";
    const res = await api.simulateMotion(d.device_id, night);
    return [`✔ movement simulated at ${d.device_id}${night ? " at night (Rule F raises an alert)" : " in the day"}`,
      `  movements in the last 24 h: ${res.motion_24h ?? "—"}`];
  },

  async sensor([id, kind, value]) {
    const usage = "sensor <id> motion on|off";
    const d = await findDevice(id, usage);
    if ((kind ?? "").toLowerCase() !== "motion") throw new UsageError(`usage: ${usage}`);
    const on = onOff(value, usage);
    await api.setProfile(d.device_id, {
      latitude: d.latitude, longitude: d.longitude, place_type: d.place_type ?? "", address: d.address ?? "", has_motion: on,
    });
    return [`✔ ${d.device_id} motion sensor ${on ? "on" : "off"}`];
  },

  async where([id]) {
    const usage = "where <id>";
    const wanted = needArg(id, usage).toUpperCase();
    const { nodes } = await api.networkTopology();
    const n = nodes.find((x) => x.node_id === wanted);
    if (!n) throw new UsageError(`unknown node "${wanted}". Known: ${nodes.map((x) => x.node_id).join(", ")}`);
    if (n.latitude == null) return [`${n.node_id} has no location yet (set it in ⚙ Configure or on the Real map).`];
    return [
      `${n.node_id}  ${n.name}`,
      `  place    ${n.place_type || "—"}`,
      `  address  ${n.address || "—"}`,
      `  coords   ${n.latitude.toFixed(5)}, ${n.longitude.toFixed(5)}`,
      `  map      https://www.openstreetmap.org/?mlat=${n.latitude}&mlon=${n.longitude}#map=16/${n.latitude}/${n.longitude}`,
    ];
  },

  async ai(words) {
    const question = needArg(words.join(" "), "ai <question>");
    const res = await api.aiChat(question, []);
    const plain = res.answer.replace(/\*\*([^*]+)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1").replace(/\*([^*\s][^*]*)\*/g, "$1");
    return [...plain.split("\n"), "", `(answered by: ${res.source})`];
  },

  async whoami() {
    const { user, auth_enabled } = await api.me();
    const where = user.company_name ? `company ${user.company_name} (sees only its own devices)` : "platform (sees every company)";
    return [`${user.username} · role ${user.role} · ${where}${auth_enabled ? "" : " (login is switched off)"}`];
  },

  async sim([action]) {
    const usage = "sim start|pause|reset";
    const calls = { start: api.startSimulation, pause: api.pauseSimulation, reset: api.resetSimulation };
    const call = calls[(action ?? "").toLowerCase()];
    if (!call) throw new UsageError(`usage: ${usage}`);
    const res = await call();
    return [`✔ simulation ${action.toLowerCase()}${res.running !== undefined ? ` · ${res.running ? "running" : "paused"}` : ""}`];
  },

  async ml([action]) {
    const usage = "ml status|train|on|off";
    const a = (action ?? "status").toLowerCase();
    if (a === "train") {
      const res = await api.mlTrain();
      return res.trained
        ? [`✔ model retrained on ${res.status.training_samples} normal readings`]
        : [`not trained: ${res.reason}`];
    }
    if (a === "on" || a === "off") {
      await api.setMl(a === "on");
      return [`✔ ML detector ${a}`];
    }
    if (a !== "status") throw new UsageError(`usage: ${usage}`);
    const s = await api.mlStatus();
    if (!s.installed) return ["ML detector not installed (pip install -r requirements-ml.txt)"];
    return [
      `enabled ${s.enabled ? "yes" : "no"} · trained ${s.trained ? "yes" : "no"} · ${s.training_samples} training readings`,
      `checked ${s.readings_checked} · flagged ${s.readings_flagged}`,
    ];
  },
};

// Split a line into words; "quoted text" stays one word.
export function tokenize(line) {
  return [...line.matchAll(/"([^"]*)"|(\S+)/g)].map((m) => m[1] ?? m[2]);
}

/** Run one command line. Returns { lines: string[], tone: "ok" | "error" }. */
export async function runCommand(line) {
  const [name, ...args] = tokenize(line.trim());
  if (!name) return { lines: [], tone: "ok" };
  const fn = COMMANDS[name.toLowerCase()];
  if (!fn) return { lines: [`unknown command "${name}". Type help to see all commands.`], tone: "error" };
  try {
    return { lines: await fn(args), tone: "ok" };
  } catch (err) {
    return { lines: [err instanceof UsageError ? err.message : `error: ${err.message}`], tone: "error" };
  }
}
