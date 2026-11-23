# Cloud MQTT broker (v2.4)

By default CyberShield uses a local Mosquitto broker. Instead, the backend, the
simulators and the ESP32 can all connect to a managed cloud broker over TLS. Nothing
else changes: same topics, same detection, same dashboard. Local mode stays the default.

```
 ESP32 / simulators ──MQTTS 8883──►  cloud broker (HiveMQ Cloud, EMQX Cloud, ...)
                                            ▲
 FastAPI backend (your PC or a cloud server) ┘──MQTTS 8883
```

## 1. Create the broker (HiveMQ Cloud, free "Serverless" plan)

1. Sign up at console.hivemq.cloud and create a **Serverless** cluster.
2. Copy the **cluster URL**, e.g. `abc123.s1.eu.hivemq.cloud` (port 8883, TLS).
3. **Access Management** -> add a credential, e.g. user `cybershield` with a long password,
   permission "Publish and Subscribe".

EMQX Cloud (Serverless) works the same way: deployment address, port 8883, an
authentication user.

## 2. Backend: set `.env`

```
MQTT_ENABLED=true
MQTT_HOST=abc123.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_TLS=true
MQTT_USERNAME=cybershield
MQTT_PASSWORD=your-broker-password
MQTT_CA_CERT=
MQTT_TOPIC_PREFIX=cybershield
```

Leave `MQTT_CA_CERT` empty: the broker's public certificate is checked with the
system CA store. Restart the backend. `/api/health` and the dashboard MQTT status show
`"mode": "cloud"`, `"tls": true`, `"connected": true`.

With Docker (`docs/CLOUD_DEPLOY.md`) put the same lines in `.env`. `MQTT_HOST` from
`.env` then replaces the `mqtt` container, which you can leave out:
`docker compose up -d db app`.

## 3. Simulators

```powershell
python iot\simulator\mqtt_simulator.py --host abc123.s1.eu.hivemq.cloud --port 8883 --tls --username cybershield --password your-broker-password
python iot\simulator\esp32_emulator.py --host abc123.s1.eu.hivemq.cloud --port 8883 --tls --username cybershield --password your-broker-password
```

No `--cafile` needed. All attack scenarios (`--scenario flood`, `spoof`, ...) work the
same over the cloud broker.

## 4. Real ESP32 board (`iot/esp32/cybershield_esp32/config.h`)

```c
#define MQTT_HOST      "abc123.s1.eu.hivemq.cloud"
#define MQTT_PORT      8883
#define MQTT_USER      "cybershield"
#define MQTT_PASS      "your-broker-password"
#define MQTT_USE_TLS   1
```

Paste the broker's root CA into `MQTT_CA_CERT`. For HiveMQ Cloud this is
**ISRG Root X1** (letsencrypt.org/certs/isrgrootx1.pem). If you leave the placeholder,
the board connects without checking the certificate. That's fine for a lab test only.

## Security notes

* One shared broker login is simpler but weaker than one login per device. Detection
  still checks the topic against the device ID (spoofing rule), and on a paid plan you
  can give each device its own credential and topic permissions.
* On a shared or public broker use a unique `MQTT_TOPIC_PREFIX` (backend) and
  `--prefix` (simulator) so other users' messages don't mix with yours.
* Never commit `.env` with the broker password.

## What was tested

* Backend with `MQTT_TLS=true` and no CA file uses the system CA store (Python `ssl`).
  Automated tests cover the local/cloud mode detection.
* Not tested: a real HiveMQ Cloud or EMQX Cloud account from this build environment.
