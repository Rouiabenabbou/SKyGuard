# Phase 11 — Real ESP32 + DHT22 Device

**Goal:** add **one real IoT device** next to the simulated ones. An ESP32
board with a DHT22 temperature/humidity sensor sends real readings over Wi-Fi
and MQTT. It appears on the dashboard, the charts, the 2D map and the 3D twin,
goes through the same security checks, and **obeys the quarantine command**:
it stops sending and blinks its LED.

**Status:**

* **Tested in the project, using the ESP32 emulator:** the device is registered,
  readings arrive with source `esp32/mqtt`, the route is `ESP32-001 → BS-5G → CORE`,
  and quarantine, release and identify commands are received.
* **Not tested here:** the Arduino sketch was not compiled or flashed to a real
  board, because no hardware or Arduino toolchain was available. It uses only
  standard library calls (PubSubClient, Adafruit DHT, ArduinoJson 7). If the
  Arduino IDE shows an error, send a screenshot.

> **Hardware is optional.** Without a board, keep `ESP32_ENABLED=false` (the
> default) and everything works as before. You can also run the **emulator**,
> which behaves exactly like the board.

---

## 1. What you need (only for the real device)

| Item | Approximate price | Note |
|---|---|---|
| ESP32 dev board (ESP32-WROOM-32 "DevKit V1") | 4–8 USD | Any ESP32 with Wi-Fi |
| DHT22 (AM2302) sensor, preferably as a **module** (3 pins, resistor included) | 2–4 USD | Bare 4-pin sensor needs a 10 kΩ resistor |
| 3 female-female jumper wires | — | |
| Micro-USB (or USB-C) **data** cable | — | Some cables only charge |

### Wiring

```
 DHT22 module          ESP32 DevKit
 ┌────────┐
 │  +  ───┼──────────► 3V3
 │ OUT ───┼──────────► GPIO 4  (D4)
 │  -  ───┼──────────► GND
 └────────┘
 (bare 4-pin DHT22: pin1=VCC, pin2=DATA, pin4=GND, plus a 10 kΩ resistor between DATA and VCC)
```

Use **3V3**, not 5V/VIN.

---

## 2. Set up Phase 11 (software, same as always)

1. Stop the backend and frontend (**Ctrl+C**).
2. Unzip **CyberShield-SatCom-3D-phase11.zip** to `D:\PROJECT\CyberShield-SatCom-3D-phase11` and open it in VS Code.
3. **Enable the ESP32.** In the project folder (next to `backend` and `frontend`),
   copy `.env.example` to a new file named `.env`, and change one line:
```
ESP32_ENABLED=true
```
4. **Terminal 1:** `cd backend` → venv → `pip install -r requirements.txt` → `uvicorn app.main:app --reload --port 8000`. You should see `v0.11.0 ready`.
5. **Terminal 2:** `cd frontend` → `npm install` → `npm run dev`.
6. On the dashboard you now see **ESP32-001 "ESP32 Lab Sensor"** (offline, waiting for the board).

### Option A: no board? Use the emulator

**Terminal 3** (in the project folder):
```
cd iot\simulator
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python esp32_emulator.py
```
ESP32-001 goes **online** within 5 s and readings appear. Press **Ctrl+C** to stop it.

### Option B: the real board

**Step 1: let the ESP32 reach Mosquitto.** Mosquitto normally accepts only
connections from your own PC. Open **PowerShell as Administrator**:
```
Stop-Service mosquitto
& "D:\Program Files\mosquitto\mosquitto.exe" -c "D:\PROJECT\CyberShield-SatCom-3D-phase11\iot\mosquitto\mosquitto.conf" -v
```
Leave this window open. Then allow port 1883 through the Windows firewall
(in another Administrator PowerShell, once):
```
New-NetFirewallRule -DisplayName "Mosquitto MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
```
Find your PC's IP address with `ipconfig` (the line **IPv4 Address**, for example `192.168.1.23`).

**Step 2: Arduino IDE.**

1. Install **Arduino IDE 2** from arduino.cc.
2. **File → Preferences → Additional boards manager URLs**:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. **Tools → Board → Boards Manager**: install **esp32 by Espressif Systems**.
4. **Tools → Manage Libraries**: install **PubSubClient** (Nick O'Leary),
   **DHT sensor library** (Adafruit, and accept "Adafruit Unified Sensor"), and
   **ArduinoJson** (Benoit Blanchon, version 7).
5. Open `iot\esp32\cybershield_esp32\cybershield_esp32.ino`.
6. In the **config.h** tab, set `WIFI_SSID`, `WIFI_PASSWORD` (2.4 GHz Wi-Fi)
   and `MQTT_HOST` (your PC's IPv4 address).
7. **Tools → Board → ESP32 Dev Module**, **Tools → Port →** the COM port of the board.
8. Click **Upload** (→). If it hangs on "Connecting…", hold the **BOOT** button on the board until it starts.
9. **Tools → Serial Monitor** at **115200 baud**. You should see:
```
=== CyberShield SatCom 3D - ESP32 field device ===
[wifi] connected, IP 192.168.1.57
[mqtt] connecting to 192.168.1.23:1883 as ESP32-001 ... connected
[send #1] {"device_id":"ESP32-001","temperature":24.3,"humidity":51.2,"battery":100,"source":"esp32"}
```

---

## 3. How it fits in the project

```
 DHT22 ──► ESP32 ──Wi-Fi──► Mosquitto ──► backend (same ingest path as every device)
                ▲                              │ checks: registered? rate? range? quarantined?
                └──── command topic ◄──────────┘ quarantine / release / identify / ping
```

* **Topics:** `cybershield/iot/ESP32-001/telemetry`, `.../status`
  (`online`, last will `offline`), and `.../command`.
* **Same security:** the Phase 5 rules apply. Warm the sensor with your hand
  above 40 °C (its allowed range is 5–40 °C) and you get an **Abnormal sensor
  value** alert.
* **Not faked:** when `ESP32_ENABLED=true` the built-in simulator skips this
  device. Its data can only come from the board or the emulator.
* **Network model:** the board uses Wi-Fi. In the twin it is drawn as
  terrestrial access through the 5G base station (`L-ESP32001-5G`).
* **Quarantine:** the backend blocks its messages (as in Phase 6) **and** the
  board itself stops sending and blinks fast. **Release** resumes it.
* **Identify:** the new **Identify** button in the 3D inspector (or
  `POST /api/devices/ESP32-001/command {"action":"identify"}`) blinks the LED 10 times.

### Changed and new files

```
iot/esp32/cybershield_esp32/cybershield_esp32.ino  NEW  firmware
iot/esp32/cybershield_esp32/config.h               NEW  Wi-Fi / broker settings
iot/mosquitto/mosquitto.conf                       NEW  broker listening on the network
iot/simulator/esp32_emulator.py                    NEW  board emulator
backend/app/config.py         CHANGED  ESP32_ENABLED, ESP32_DEVICE_ID, version 0.11.0
backend/app/seed.py           CHANGED  registers ESP32-001 + its link when enabled
backend/app/simulation_controller.py CHANGED  never simulates physical devices
backend/app/routes/devices.py CHANGED  POST /api/devices/{id}/command
.env.example                  CHANGED  Phase 8, 9 and 11 settings
frontend: NetworkMap (position), TwinPanel (Identify button), api.js
```

---

## 4. Test Phase 11

| # | Test | How | Expected result |
|---|---|---|---|
| 1 | Registered | `.env` with `ESP32_ENABLED=true`, start the backend | ESP32-001 card (offline) and a node in 2D/3D |
| 2 | Online | Start the emulator or the board | Online within 5 s; readings every 5 s; source `esp32/mqtt` in Live telemetry |
| 3 | Charts | Overview | A 4th (yellow) line on temperature/humidity |
| 4 | Route | Network tab | `ESP32-001 → BS-5G → CORE` |
| 5 | Identify | 4D Twin → click ESP32-001 → **Identify** | Emulator prints `identify`, or the board LED blinks 10 times |
| 6 | Quarantine | **Quarantine** on its card | Emulator/board prints `QUARANTINED`, stops sending; real board LED blinks fast |
| 7 | Release | **Release** | Readings resume |
| 8 | Abnormal (real board) | Hold the DHT22 in your hand / breathe on it | Humidity rises; above 90 % gives an alert |
| 9 | Power loss (real board) | Unplug the USB cable | About 45 s later, "offline" (last will); event log entry |
| 10 | Disabled | `ESP32_ENABLED=false`, new database (Reset) | Nothing changes for the other devices |

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| Serial: `[wifi] FAILED` | Wrong SSID/password, or a 5 GHz-only network. Use a 2.4 GHz network or phone hotspot |
| Serial: `failed (state -2)` | The board can't reach Mosquitto: use the PC's IPv4 (not localhost), run Mosquitto with `mosquitto.conf`, add the firewall rule, same Wi-Fi network |
| Serial: `[dht22] read failed` | Check the wiring: DATA on GPIO 4, 3V3, GND; add the 10 kΩ resistor for a bare sensor |
| ESP32-001 not on the dashboard | `.env` must be in the project root with `ESP32_ENABLED=true`; restart the backend |
| Board online but "Unauthorized device" alert | `DEVICE_ID` in config.h must equal `ESP32_DEVICE_ID` in .env |
| Upload stuck on "Connecting…" | Hold BOOT during upload; try another USB cable (data cable) |
| Mosquitto window: "Only one usage of each socket address" | The service is still running: `Stop-Service mosquitto` first |

**Security note:** `mosquitto.conf` allows anonymous clients so the demo is easy.
Use it only on your own network. For more, create a password file
(`mosquitto_passwd -c passwd roya`), set `allow_anonymous false` and
`password_file ...` in the config, and fill in `MQTT_USER`/`MQTT_PASS` in
`config.h` and `MQTT_USERNAME`/`MQTT_PASSWORD` in `.env`.

---

## Next: Phase 12 — Testing, optional ML and final documentation

Automated tests for the backend, an optional machine-learning anomaly
detector (scikit-learn), and the final docs: README, architecture, test report
and demo script.
