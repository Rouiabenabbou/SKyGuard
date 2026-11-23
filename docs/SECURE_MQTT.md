# Secure MQTT (v1.1)

By default the project uses an open Mosquitto broker on port 1883, which is fine
for a quick demo. Version 1.1 adds a **secure broker setup**:

| Protection | What it stops |
|---|---|
| **No anonymous clients** | unknown programs can't connect at all |
| **One user name + password per device** (user = device ID) | a device needs its own secret to send data |
| **ACL (access control list)** | a device may only write to *its own* topics, so IOT-001 can't pretend to be IOT-002 (spoofing) |
| **TLS on port 8883** | nobody on the Wi-Fi can read or change the messages |

Everything stays on your own computer and your own Wi-Fi.

## Files

| File | Purpose |
|---|---|
| `iot/mosquitto/setup_secure_mqtt.py` | creates the passwords, the certificates and a ready broker config |
| `iot/mosquitto/mosquitto-secure.conf` | template of the secure broker config (for reading) |
| `iot/mosquitto/acl.conf` | who may read / write which topics |
| `iot/mosquitto/passwd`, `credentials.txt`, `certs/`, `mosquitto-secure.local.conf` | **generated, private, not in git** |

## Steps (Windows, PowerShell)

1. Stop the Mosquitto service if it runs (it uses port 1883):
   ```powershell
   net stop mosquitto        # in an Administrator PowerShell
   ```
2. Create passwords and certificates (from the project folder, venv active):
   ```powershell
   python iot\mosquitto\setup_secure_mqtt.py --mosquitto-dir "C:\Program Files\mosquitto"
   ```
   * `openssl` is needed for TLS. Git for Windows includes it
     (`C:\Program Files\Git\usr\bin`). Without it, use `--no-tls` (passwords + ACL only).
   * For a real ESP32, add the PC's IP so the certificate is valid for it:
     `--host 192.168.1.20`.
3. The script prints lines for `.env`. Copy them into the project's `.env`:
   ```
   MQTT_USERNAME=backend
   MQTT_PASSWORD=<printed password>
   MQTT_TLS=true
   MQTT_PORT=8883
   MQTT_CA_CERT=D:\...\iot\mosquitto\certs\ca.crt
   ```
4. Start the broker with the generated config (it has full paths):
   ```powershell
   & "C:\Program Files\mosquitto\mosquitto.exe" -c "D:\...\iot\mosquitto\mosquitto-secure.local.conf" -v
   ```
5. Restart the backend. The **MQTT broker** card shows *Online*, and
   `GET /api/mqtt/status` shows `"authenticated": true, "tls": true`.

## Simulators with the secure broker

The device passwords are in `iot/mosquitto/credentials.txt`.

```powershell
# all simulated devices, encrypted
python iot\simulator\mqtt_simulator.py --credentials iot\mosquitto\credentials.txt --tls --port 8883 --cafile iot\mosquitto\certs\ca.crt

# one ESP32 emulator, with a motion sensor
python iot\simulator\esp32_emulator.py --username ESP32-001 --password <from credentials.txt> --tls --port 8883 --cafile iot\mosquitto\certs\ca.crt --motion
```

## Real ESP32

In `iot/esp32/.../config.h`:

```c
#define MQTT_PORT      8883
#define MQTT_USER      "ESP32-001"
#define MQTT_PASS      "<from credentials.txt>"
#define MQTT_USE_TLS   1
// paste the content of iot/mosquitto/certs/ca.crt into MQTT_CA_CERT
```

## Test it (what we checked)

| Test | Expected |
|---|---|
| Connect without a password | refused (`Not authorized`) |
| Connect with a wrong password | refused |
| Backend connects on 8883 with TLS | MQTT card *Online* |
| IOT-001 publishes to `cybershield/devices/IOT-002/telemetry` | dropped by the ACL; nothing stored for IOT-002 |
| `mosquitto_sub` on 8883 without the CA file | TLS handshake fails |

## Back to the simple broker

Remove the MQTT_* lines from `.env` (or set `MQTT_TLS=false`), stop the secure
broker and start Mosquitto normally.
