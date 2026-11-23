"""
Central configuration for the backend.

Values are read from environment variables (or a .env file in the project
root), with safe defaults so the app runs with zero setup.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> project root is two folders up from backend/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

APP_NAME = "CyberShield SatCom 3D"
APP_VERSION = "2.6.0"  # v2.1: SOC stages 2-4 (threat hunting, threat intel, AI analyst tools, roles, MFA, approvals)

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Origins allowed to call the API from a browser (the Vite dev server).
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

# How often (seconds) the backend pushes a heartbeat over the WebSocket.
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "2"))

# ---------------------------------------------------------------- Phase 2
# SQLite database file. Created automatically on first start.
DATABASE_DIR = PROJECT_ROOT / "database"
EXPORTS_DIR = Path(os.getenv("EXPORTS_DIR", str(PROJECT_ROOT / "exports")))  # CSV files saved by the dashboard
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_DIR / 'cybershield.db'}")
# v1.3: accept the usual postgres:// form and use the psycopg 3 driver (pip install -r requirements-cloud.txt)
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]
# v1.3: the built dashboard (npm run build). When it exists the backend serves it too: one URL for everything.
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", str(PROJECT_ROOT / "frontend" / "dist")))

# Built-in IoT simulator.
SIM_INTERVAL = float(os.getenv("SIM_INTERVAL", "5"))      # seconds between readings per device
SIM_AUTOSTART = os.getenv("SIM_AUTOSTART", "true").lower() == "true"

# A device that sends nothing for this many seconds is shown as offline.
OFFLINE_AFTER = float(os.getenv("OFFLINE_AFTER", "15"))

# ---------------------------------------------------------------- Phase 3
# MQTT broker (Mosquitto). If it is not running, the app keeps working and
# the built-in simulator sends data directly instead.
MQTT_ENABLED = os.getenv("MQTT_ENABLED", "true").lower() == "true"
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "cybershield")

# ---------------------------------------------------------------- Phase 4
# Random "rain fade" events that degrade the satellite link now and then.
NET_RANDOM_EVENTS = os.getenv("NET_RANDOM_EVENTS", "true").lower() == "true"

# ---------------------------------------------------------------- Phase 5
# Detection thresholds. Change them in .env to tune the detection engine.
RATE_WINDOW_SECONDS = float(os.getenv("RATE_WINDOW_SECONDS", "5"))
RATE_THRESHOLD_PER_SEC = float(os.getenv("RATE_THRESHOLD_PER_SEC", "10"))  # normal is 0.2 msg/s
CONN_WINDOW_SECONDS = float(os.getenv("CONN_WINDOW_SECONDS", "30"))
CONN_THRESHOLD = int(os.getenv("CONN_THRESHOLD", "5"))  # connections per window
ABNORMAL_MARGIN = float(os.getenv("ABNORMAL_MARGIN", "15"))  # this far outside range = high severity
ALERT_COOLDOWN_SECONDS = float(os.getenv("ALERT_COOLDOWN_SECONDS", "30"))  # no duplicate alerts within this time

# ---------------------------------------------------------------- Phase 6
# Automatically quarantine a device when one of these alerts fires for it.
# Can also be switched on/off from the dashboard while running.
AUTO_QUARANTINE = os.getenv("AUTO_QUARANTINE", "true").lower() == "true"
AUTO_QUARANTINE_ALERTS = [
    a.strip() for a in os.getenv(
        "AUTO_QUARANTINE_ALERTS", "excessive_message_rate,suspicious_connections,device_id_spoofing"
    ).split(",") if a.strip()
]

# ---------------------------------------------------------------- Phase 8
# Satellite -> 5G failover. Can also be switched on/off from the dashboard.
FAILOVER_ENABLED = os.getenv("FAILOVER_ENABLED", "true").lower() == "true"
HANDOVER_DELAY_MIN = float(os.getenv("HANDOVER_DELAY_MIN", "1.5"))  # simulated re-attach time, seconds
HANDOVER_DELAY_MAX = float(os.getenv("HANDOVER_DELAY_MAX", "3.0"))
FAILBACK_STABLE_SECONDS = float(os.getenv("FAILBACK_STABLE_SECONDS", "10"))  # primary must be healthy this long
FAILOVER_ON_DEGRADED = os.getenv("FAILOVER_ON_DEGRADED", "true").lower() == "true"
DEGRADED_FAILOVER_SECONDS = float(os.getenv("DEGRADED_FAILOVER_SECONDS", "6"))  # degraded this long -> fail over
DRILL_SECONDS = float(os.getenv("DRILL_SECONDS", "30"))  # length of the "satellite outage drill"

# ---------------------------------------------------------------- Phase 9
# 4D timeline: a snapshot of the twin is stored every network tick (2 s).
# Older snapshots are deleted above this number (5400 = about 3 hours).
TIMELINE_MAX_SNAPSHOTS = int(os.getenv("TIMELINE_MAX_SNAPSHOTS", "5400"))

# ---------------------------------------------------------------- Phase 11
# A real ESP32 + DHT22 board. When enabled, the device is registered (with its
# own 5G/Wi-Fi access link) and the built-in simulator does NOT fake it: its
# data must come from the board (or from iot/simulator/esp32_emulator.py).
ESP32_ENABLED = os.getenv("ESP32_ENABLED", "false").lower() == "true"
ESP32_DEVICE_ID = os.getenv("ESP32_DEVICE_ID", "ESP32-001")
PHYSICAL_DEVICES = [ESP32_DEVICE_ID] if ESP32_ENABLED else []

# ---------------------------------------------------------------- Phase 12
# Optional machine-learning anomaly detector (needs: pip install -r requirements-ml.txt).
# It learns what "normal" readings look like and flags unusual ones, next to the rules.
ML_ENABLED = os.getenv("ML_ENABLED", "false").lower() == "true"
ML_MIN_TRAINING_READINGS = int(os.getenv("ML_MIN_TRAINING_READINGS", "120"))  # ~3-4 min of simulation
ML_CONTAMINATION = float(os.getenv("ML_CONTAMINATION", "0.01"))  # expected share of outliers in training
ML_MARGIN = float(os.getenv("ML_MARGIN", "1.0"))  # how far below normal a score must be to alert

# ------------------------------------------------- v1.1: login, roles, audit
# Every API call needs a login token, except /api/health and /api/auth/login.
# Roles: viewer (read only) < operator (respond to incidents) < admin (everything).
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
AUTH_TOKEN_HOURS = float(os.getenv("AUTH_TOKEN_HOURS", "12"))
# Accounts created on the first start (change the passwords after the first login!).
DEFAULT_USERS = [
    (os.getenv("ADMIN_USER", "admin"), os.getenv("ADMIN_PASSWORD", "Admin@2026"), "admin"),
    (os.getenv("OPERATOR_USER", "operator"), os.getenv("OPERATOR_PASSWORD", "Operator@2026"), "operator"),
    (os.getenv("VIEWER_USER", "viewer"), os.getenv("VIEWER_PASSWORD", "Viewer@2026"), "viewer"),
]
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))  # wrong passwords before a lock
LOGIN_LOCK_SECONDS = float(os.getenv("LOGIN_LOCK_SECONDS", "60"))

# ------------------------------------------------- v1.1: secure MQTT (TLS)
# Username/password: MQTT_USERNAME / MQTT_PASSWORD above. TLS: set MQTT_TLS=true,
# MQTT_PORT=8883 and MQTT_CA_CERT to the CA file made by iot/mosquitto/make_certs.
MQTT_TLS = os.getenv("MQTT_TLS", "false").lower() == "true"
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT") or None

# ------------------------------------------------- v2.4: cloud MQTT broker
# Point MQTT_HOST at a managed broker (HiveMQ Cloud, EMQX Cloud, ...) with
# MQTT_TLS=true, MQTT_PORT=8883 and the broker login. Leave MQTT_CA_CERT empty:
# the broker's public certificate is then checked with the system CA store.
# See docs/CLOUD_MQTT.md. Empty client ID = a new one on every start.
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID") or None
LOCAL_MQTT_HOSTS = {"localhost", "127.0.0.1", "::1", "mqtt", "mosquitto"}
MQTT_MODE = "local" if (MQTT_HOST.lower() in LOCAL_MQTT_HOSTS or MQTT_HOST.startswith(("192.168.", "10."))) else "cloud"

# ------------------------------------------------- v1.1: motion sensors (PIR)
# Movement between these hours (local time, 24 h clock) raises a "movement at night" alert.
MOTION_NIGHT_START = int(os.getenv("MOTION_NIGHT_START", "22"))
MOTION_NIGHT_END = int(os.getenv("MOTION_NIGHT_END", "6"))
MOTION_ALERT_ALWAYS = os.getenv("MOTION_ALERT_ALWAYS", "false").lower() == "true"  # demo: alert at any hour

# ------------------------------------------------- v1.1: free AI assistant
# Works without a key (built-in offline analyst). With a free key it uses a real LLM:
#   gemini     -> https://aistudio.google.com/apikey        (free tier)
#   groq       -> https://console.groq.com/keys             (free tier)
#   openrouter -> https://openrouter.ai/keys                (free ":free" models)
# v2.5: Huawei Cloud ModelArts Studio (MaaS) is the default (docs/HUAWEI_AI.md):
#   huawei     -> console.huaweicloud.com -> ModelArts Studio (MaaS) -> API Keys
# v2.6: DeepSeek is the default (docs/DEEPSEEK_AI.md):
#   deepseek   -> https://platform.deepseek.com/api_keys
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek").lower()
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
HUAWEI_MAAS_URL = os.getenv("HUAWEI_MAAS_URL", "https://api-ap-southeast-1.modelarts-maas.com/v1")
HUAWEI_MAAS_MODEL = os.getenv("HUAWEI_MAAS_MODEL", "DeepSeek-V3")
AI_API_KEY = os.getenv("AI_API_KEY") or None
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or None
if AI_PROVIDER == "deepseek" and not AI_API_KEY:
    AI_API_KEY = DEEPSEEK_API_KEY  # DEEPSEEK_API_KEY works as the key for the deepseek provider
AI_MODEL = os.getenv("AI_MODEL") or None  # empty = the provider's default below
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "30"))
# v1.5: address of a self-hosted OmniRoute (or any OpenAI-compatible) gateway.
# In Docker use http://host.docker.internal:20128/v1 to reach OmniRoute on the host.
OMNIROUTE_URL = os.getenv("OMNIROUTE_URL", "http://localhost:20128/v1")

# ---- v1.2: many companies on one system (multi-tenant, see tenancy.py)
# Demo companies created on the first start of v1.2: (id, name, sector, devices, admin user, admin password).
# Change the passwords after the first login. SEED_DEMO_COMPANIES=false starts with no companies.
SEED_DEMO_COMPANIES = os.getenv("SEED_DEMO_COMPANIES", "true").lower() == "true"
DEMO_COMPANIES = [
    ("atlas-farms", "Atlas Dairy Farms", "farm", ["IOT-003"], "farm_admin", "Farm@2026"),
    ("casa-offices", "Casa Business Center", "offices", ["IOT-002"], "offices_admin", "Offices@2026"),
    ("sahara-solar", "Sahara Solar", "energy", ["IOT-001"], "solar_admin", "Solar@2026"),
]

# ---- v1.2: phone alarm (see notifier.py and docs/PHONE_ALARM.md). Can also be set in Admin -> Phone alarm.
NOTIFY_ENABLED = os.getenv("NOTIFY_ENABLED", "false").lower() == "true"
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")  # long and secret, e.g. cybershield-roya-8f3k2q
NOTIFY_MIN_SEVERITY = os.getenv("NOTIFY_MIN_SEVERITY", "medium")  # medium = every simulated attack
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---- v1.3: long-term data (warehouse.py)
ROLLUP_INTERVAL_SECONDS = float(os.getenv("ROLLUP_INTERVAL_SECONDS", "300"))  # summarise live readings every 5 min

# ---- v1.4
# Three bigger demo customers (mine, hospital, cold-chain logistics) with 6 more devices, added once.
SEED_BIG_COMPANIES = os.getenv("SEED_BIG_COMPANIES", "true").lower() == "true"
# Prometheus metrics at /metrics for cloud monitoring: set a secret token to switch it on
# (the scraper sends "Authorization: Bearer <token>"). Empty = /metrics is off.
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")

# ---- v2.1 SOC stages 2-4
# Security event store (Threat Hunting). Events older than this are deleted automatically.
SECURITY_EVENT_RETENTION_DAYS = float(os.getenv("SECURITY_EVENT_RETENTION_DAYS", "7"))
FLOW_SUMMARY_SECONDS = float(os.getenv("FLOW_SUMMARY_SECONDS", "60"))  # one MQTT flow record per device per minute
# Network detection thresholds (rules CS-011 ... CS-021)
BRUTE_FORCE_THRESHOLD = int(os.getenv("BRUTE_FORCE_THRESHOLD", "5"))  # failed MQTT logins from one address
BRUTE_FORCE_WINDOW_SECONDS = float(os.getenv("BRUTE_FORCE_WINDOW_SECONDS", "60"))
PORT_SCAN_THRESHOLD = int(os.getenv("PORT_SCAN_THRESHOLD", "15"))  # distinct ports from one address
PORT_SCAN_WINDOW_SECONDS = float(os.getenv("PORT_SCAN_WINDOW_SECONDS", "30"))
BEACON_MIN_CONNECTIONS = int(os.getenv("BEACON_MIN_CONNECTIONS", "6"))
BEACON_MAX_JITTER = float(os.getenv("BEACON_MAX_JITTER", "0.25"))  # std / mean of the intervals
EXFIL_BYTES_PER_MINUTE = int(os.getenv("EXFIL_BYTES_PER_MINUTE", str(5 * 1024 * 1024)))
G5_AUTH_FAIL_THRESHOLD = int(os.getenv("G5_AUTH_FAIL_THRESHOLD", "4"))
GNSS_MIN_CN0 = float(os.getenv("GNSS_MIN_CN0", "25"))  # dB-Hz; below this with no fix = jamming indicator
GNSS_MAX_SPEED_MPS = float(os.getenv("GNSS_MAX_SPEED_MPS", "300"))  # faster than this for a fixed device = spoofing
# Threat intelligence enrichment (optional, free tiers). Keys stay on the server, never in the browser.
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
ABUSEIPDB_API_KEY = os.getenv("ABUSEIPDB_API_KEY", "")
OTX_API_KEY = os.getenv("OTX_API_KEY", "")
INTEL_TIMEOUT = float(os.getenv("INTEL_TIMEOUT", "8"))
SEED_DEMO_IOCS = os.getenv("SEED_DEMO_IOCS", "true").lower() == "true"
# Approvals: true = the person who asked for a containment can't approve it themselves (two-person rule).
APPROVAL_TWO_PERSON = os.getenv("APPROVAL_TWO_PERSON", "false").lower() == "true"
# SOC analyst demo accounts (L1 / L2 / L3 / SOC manager), created once.
SEED_SOC_USERS = os.getenv("SEED_SOC_USERS", "true").lower() == "true"
SOC_USERS = [
    ("analyst_l1", "AnalystL1@2026", "soc_l1"),
    ("analyst_l2", "AnalystL2@2026", "soc_l2"),
    ("analyst_l3", "AnalystL3@2026", "soc_l3"),
    ("soc_manager", "Manager@2026", "soc_manager"),
]
# Roles that must use two-factor login (comma list, e.g. "admin,soc_manager"). Empty = optional for everyone.
MFA_REQUIRED_ROLES = [r.strip() for r in os.getenv("MFA_REQUIRED_ROLES", "").split(",") if r.strip()]

# ---- v2.2 Huawei Cloud: IoTDA bridge and ModelArts / MindSpore anomaly model
IOTDA_PUSH_TOKEN = os.getenv("IOTDA_PUSH_TOKEN", "")  # secret in the IoTDA data forwarding URL; empty = bridge off
IOTDA_REGION = os.getenv("IOTDA_REGION", "")  # e.g. cn-north-4 (shown on the status page only)
AE_MODEL_PATH = os.getenv("AE_MODEL_PATH") or str(Path(__file__).resolve().parent.parent / "models" / "anomaly_ae.json")
AE_ENABLED = os.getenv("AE_ENABLED", "true").lower() == "true"
LAB_SEND_INTERVAL_SECONDS = float(os.getenv("LAB_SEND_INTERVAL_SECONDS", "5"))  # ESP32 SEND_EVERY_MS / 1000
