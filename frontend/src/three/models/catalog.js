// Which 3D model and which (typical, real-world) hardware each IoT device uses.
// The devices are simulated; the parts are the kind of components such a device is built from.

export function iotKind(device = {}) {
  const t = `${device.device_type ?? ""} ${device.device_name ?? ""} ${device.device_id ?? ""}`.toLowerCase();
  if (t.includes("esp32")) return "esp32";
  if (t.includes("container") || t.includes("reefer")) return "container";
  if (t.includes("fridge") || t.includes("freezer") || t.includes("cold")) return "fridge";
  if (t.includes("vibration") || t.includes("conveyor")) return "vibration";
  if (t.includes("building") || t.includes("office") || t.includes("room")) return "building";
  if (t.includes("agri") || t.includes("farm") || t.includes("soil") || t.includes("livestock")) return "agri";
  if (t.includes("environment") || t.includes("air") || t.includes("weather") || t.includes("desert")) return "station";
  return "generic";
}

// title, parts (shown as hotspots: [name, what it does, [x, y, z]]) and the spec sheet.
export const HARDWARE = {
  esp32: {
    title: "ESP32 DevKit + DHT22 on a breadboard",
    parts: [
      ["ESP32-WROOM-32", "Dual-core 240 MHz MCU with Wi-Fi + Bluetooth", [-0.12, 0.2, 0.05]],
      ["DHT22 / AM2302", "Temperature ±0.5 °C, humidity ±2 % RH", [0.33, 0.33, 0.05]],
      ["PCB antenna", "2.4 GHz Wi-Fi to the access point → MQTT", [-0.12, 0.2, -0.24]],
      ["USB port", "5 V power and programming (Arduino IDE)", [-0.12, 0.15, 0.32]],
      ["Status LED", "Blinks on 'identify', off when quarantined", [0.0, 0.2, 0.2]],
    ],
    specs: [["Microcontroller", "ESP32-WROOM-32, 240 MHz, 520 KB RAM"], ["Sensor", "DHT22 (AM2302)"],
      ["Radio", "Wi-Fi 802.11 b/g/n → MQTT"], ["Power", "USB 5 V or 3.7 V Li-ion"], ["Firmware", "Arduino / PlatformIO sketch"]],
  },
  station: {
    title: "Solar environmental monitoring station",
    parts: [
      ["Radiation shield", "Louvered shield with an SHT31 temperature/humidity sensor", [0.0, 0.62, 0.12]],
      ["Solar panel", "10 W panel charges the battery", [0.0, 0.93, -0.12]],
      ["Logger + modem", "Data logger with a satellite / LTE-M modem in an IP67 box", [0.0, 0.33, 0.12]],
      ["Antenna", "Uplink antenna", [0.14, 1.12, 0]],
      ["PIR sensor", "Motion sensor (HC-SR501 class) for intruders at night", [0.0, 0.24, 0.16]],
    ],
    specs: [["Sensors", "SHT31 temp/humidity, PIR motion"], ["Uplink", "Satellite IoT modem (backup 5G)"],
      ["Power", "10 W solar + 12 V LiFePO4 battery"], ["Enclosure", "IP67 polycarbonate, steel mast"], ["Interval", "1 reading / 5 s (demo)"]],
  },
  agri: {
    title: "Smart farming sensor stake",
    parts: [
      ["Soil probe", "Capacitive soil moisture + temperature probe", [0.0, 0.08, 0.06]],
      ["Sensor head", "Air temperature / humidity sensor", [0.0, 0.52, 0.1]],
      ["Solar cell", "Small solar cell keeps it running", [0.0, 0.74, -0.06]],
      ["Antenna", "Satellite IoT antenna (works far from towers)", [0.1, 0.95, 0]],
      ["PIR sensor", "Motion: animals escaping or intruders at night", [0.0, 0.4, 0.12]],
    ],
    specs: [["Sensors", "SHT40 air, capacitive soil probe, PIR"], ["Uplink", "Satellite IoT, backup 5G"],
      ["Power", "Solar cell + Li-SOCl₂ battery"], ["Install", "Pushed into the ground in the field"], ["Rating", "IP68"]],
  },
  building: {
    title: "Wall-mounted smart building sensor",
    parts: [
      ["Display", "E-ink display with the current value", [0.0, 0.58, 0.1]],
      ["Sensor vents", "BME680: temperature, humidity, air quality", [0.0, 0.36, 0.1]],
      ["Status LED", "Green = OK, red = alarm", [0.15, 0.7, 0.1]],
      ["5G module", "5G / LTE-M module inside", [0.0, 0.45, -0.02]],
    ],
    specs: [["Sensors", "BME680 temp/humidity/VOC, PIR (optional)"], ["Uplink", "5G NR / LTE-M"],
      ["Power", "PoE or 2 × AA lithium"], ["Mount", "Indoor wall, 1.5 m high"], ["Size", "86 × 86 × 30 mm"]],
  },
  fridge: {
    title: "Cold storage unit with a temperature logger",
    parts: [
      ["Probe", "PT100 probe in a glycol bottle (stable reading)", [0.0, 0.45, 0.2]],
      ["Logger", "Data logger with display and alarm buzzer", [0.0, 0.82, 0.24]],
      ["Door sensor", "Reed switch: door open too long = alarm", [0.22, 0.62, 0.24]],
      ["5G module", "Sends readings every few seconds", [0.0, 0.98, 0.0]],
    ],
    specs: [["Sensors", "PT100 probe (±0.1 °C), door reed switch"], ["Range", "−40 … +20 °C"],
      ["Uplink", "5G / LTE-M"], ["Power", "Mains + 48 h backup battery"], ["Use", "Vaccines, food, medicine"]],
  },
  container: {
    title: "Refrigerated shipping container (reefer) with a tracker",
    parts: [
      ["Reefer unit", "Cooling machine at the front of the container", [0.62, 0.28, 0.0]],
      ["Tracker", "GPS + satellite tracker on the roof", [0.0, 0.62, 0.0]],
      ["Probe", "Return-air temperature probe", [0.45, 0.4, 0.2]],
      ["Doors", "Door sensor (tamper alarm)", [-0.62, 0.3, 0.0]],
    ],
    specs: [["Sensors", "Supply/return air probes, door, GPS"], ["Uplink", "Satellite (at sea) + 4G/5G in port"],
      ["Power", "Ship / reefer power + backup battery"], ["Container", "40 ft high-cube reefer"], ["Range", "−30 … +30 °C"]],
  },
  vibration: {
    title: "Industrial vibration sensor on a conveyor motor",
    parts: [
      ["Vibration puck", "3-axis MEMS accelerometer (ADXL355 class)", [0.0, 0.5, 0.16]],
      ["Motor", "Conveyor drive motor being monitored", [0.0, 0.3, 0.0]],
      ["Gateway", "5G industrial gateway on the frame", [0.36, 0.5, 0.0]],
      ["Belt", "Conveyor belt", [-0.3, 0.32, 0.0]],
    ],
    specs: [["Sensors", "3-axis accelerometer, temperature"], ["Uplink", "5G private network"],
      ["Power", "10-year battery"], ["Mount", "Magnet on the motor housing"], ["Rating", "IP69K, ATEX zone 2"]],
  },
  generic: {
    title: "IoT sensor node",
    parts: [
      ["Enclosure", "Weather-proof box with the electronics", [0.0, 0.35, 0.12]],
      ["Antenna", "Radio uplink", [0.12, 0.85, 0.0]],
      ["Sensor", "Temperature / humidity sensor", [0.0, 0.2, 0.14]],
    ],
    specs: [["Sensors", "Temperature, humidity"], ["Uplink", "Satellite or 5G"], ["Power", "Battery"], ["Rating", "IP66"]],
  },
};

// The shared network equipment (simulated: no real satellite or 5G core is used).
export const INFRA_HARDWARE = {
  satellite: {
    title: "Communications satellite (LEO, simulated)",
    parts: [
      ["Main dish", "Earth-facing antenna for the IoT uplink", [0, 0.5, 0.16]],
      ["Solar wings", "Solar arrays power the satellite", [0.55, 0.5, 0]],
      ["Bus", "Body with batteries, computer and radios (gold insulation)", [0, 0.62, 0]],
    ],
    specs: [["Orbit", "Low Earth orbit (not to scale in the twin)"], ["Uplink", "Ka/Ku-band to the ground station"],
      ["IoT access", "Satellite IoT terminals"], ["Power", "2 solar wings + Li-ion"], ["In this project", "Simulated"]],
  },
  ground_station: {
    title: "Satellite ground station (teleport)",
    parts: [
      ["Dish", "Tracks the satellite (az/el mount)", [-0.12, 0.62, 0.1]],
      ["Shelter", "Modems, amplifiers and the fibre to the core", [0.36, 0.3, 0.32]],
    ],
    specs: [["Antenna", "Parabolic, az/el tracking"], ["Link", "Satellite ↔ fibre to the 5G core"], ["In this project", "Simulated"]],
  },
  base_station: {
    title: "5G base station (gNodeB) on a lattice tower",
    parts: [
      ["Sector antennas", "3 sectors × 2 massive-MIMO panels", [0.09, 0.86, 0.05]],
      ["Backhaul dish", "Microwave link to the core", [0, 0.58, 0.12]],
      ["Cabinet", "Baseband unit and power", [0.22, 0.2, 0.22]],
      ["Warning light", "Aircraft warning light", [0, 1.04, 0]],
    ],
    specs: [["Radio", "5G NR, 3 sectors"], ["Role", "Backup path when the satellite fails (failover)"], ["In this project", "Simulated"]],
  },
  core: {
    title: "5G core / data centre",
    parts: [["Building", "Core network functions (AMF, SMF, UPF)", [0, 0.3, 0.26]], ["Chillers", "Cooling", [0, 0.52, 0]]],
    specs: [["Functions", "AMF, SMF, UPF (modelled)"], ["Links", "Fibre to the ground station and towers"], ["In this project", "Simulated"]],
  },
  security_server: {
    title: "Security operations centre (SOC) servers",
    parts: [["Server racks", "Detection engine, database, dashboard", [0.17, 0.4, 0.18]], ["Shield", "CyberShield monitoring", [0, 0.85, 0]]],
    specs: [["Software", "This project's backend (FastAPI)"], ["Detection", "Rules A–F + optional ML"], ["In this project", "Runs on your computer / cloud"]],
  },
};
