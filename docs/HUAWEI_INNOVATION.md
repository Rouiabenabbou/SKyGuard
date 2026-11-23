# CyberShield SOC for the Huawei ICT Competition (Innovation track)

## 1. Pitch (one paragraph)

**CyberShield SOC: an AI security operations center for satellite-5G IoT, with human-approved response.**
Remote IoT sensors (farms, mines, hospitals, cold chain) increasingly reach the internet through satellite
and 5G links. These networks are attacked (MQTT brute force, botnets, GNSS jamming and spoofing), but small
operators have no security team. CyberShield watches every device and link and detects attacks with rules
and a machine-learning model. An AI analyst investigates them through controlled tools and cites the
evidence for every claim. A containment action such as isolating a device runs only after a person
approves it. Everything is shown in a live 3D digital twin of the network.

**What is new:** (1) one SOC for the space, 5G and IoT layers together, including GNSS attacks;
(2) an AI analyst that may only read through audited tools, must cite evidence, and cannot act alone;
(3) human-in-the-loop containment with 2FA and a tamper-evident audit log.

## 2. Huawei technology used

| Huawei service | Used for | Where in the code |
|---|---|---|
| **Huawei Cloud ECS** | Runs the app (Docker Compose) | `Dockerfile`, `docker-compose.yml`, `docs/CLOUD_DEPLOY.md` |
| **RDS for PostgreSQL** | Database | `DATABASE_URL`, `requirements-cloud.txt` |
| **IoTDA** | Real devices connect over MQTTS; readings are pushed to the app | `iot/esp32/.../config.h` (`USE_IOTDA`), `backend/app/iotda.py` |
| **ModelArts + MindSpore** | Trains the anomaly detection model | `ml/modelarts/train.py`, `backend/app/ml_autoencoder.py` |
| **OBS** | Stores training data and the trained model | ModelArts input / output folders |

## 3. Step 1: deploy on Huawei Cloud (ECS + RDS)

Follow `docs/CLOUD_DEPLOY.md`: an ECS server (Ubuntu, 2 vCPU / 4 GB), optionally RDS for PostgreSQL, then
`docker compose up -d`. In the ECS security group, open port 8000 (or 443 behind Nginx). Add to `.env`:

```
IOTDA_PUSH_TOKEN=<a long random text>
IOTDA_REGION=cn-north-4
```

## 4. Step 2: connect the ESP32 through IoTDA

1. IoTDA console → create a free (basic) instance if asked.
2. **Products → Create product**: protocol MQTT, data type JSON. In the product model, add a service
   `Sensor` with properties `temperature` (decimal), `humidity` (decimal), `battery` (decimal),
   `motion` (boolean).
3. **Devices → Register device**: node ID `ESP32-001` (must match the device ID in CyberShield). Copy the
   **device ID** and **secret** shown at the end.
4. In `iot/esp32/cybershield_esp32/config.h` set `USE_IOTDA 1`, `IOTDA_HOST` (Overview → Access Details →
   MQTTS address), `IOTDA_DEVICE_ID`, `IOTDA_SECRET`, and paste the device CA certificate from Access
   Details. Upload to the board. The serial monitor should show `[iotda] ... connected`, and the device turns
   online in the IoTDA console.
5. **Rules → Data Forwarding → Create rule**: data source *Device property*, trigger *Device property
   reported*, target **HTTP/HTTPS push**, URL
   `http(s)://<ECS address>:8000/api/iotda/push?token=<IOTDA_PUSH_TOKEN>`. Start the rule.
6. In CyberShield, **System Health → Huawei Cloud and lab test** shows the pushes, and the device shows LAB
   readings.

Commands: quarantine / release / identify can be sent to the board from the IoTDA console
(*Devices → Commands*, command name `quarantine`, `release` or `identify`). CyberShield's own quarantine
button acts on the simulator and the local MQTT broker. Sending commands from CyberShield through the IoTDA
application API is future work.

## 5. Step 3: train the anomaly model on ModelArts (MindSpore)

1. Export normal data: `GET /api/export/telemetry.csv` (open it in the browser while logged in). Attack
   readings are skipped by the script.
2. OBS: create a bucket with the folders `code/`, `data/` and `output/`. Upload `ml/modelarts/train.py` to
   `code/` and `telemetry.csv` to `data/`.
3. ModelArts → **Training Management → Training Jobs → Create**:
   * algorithm type *Custom*, boot mode *Preset image* → **MindSpore** (a CPU image is enough)
   * code directory `obs://<bucket>/code/`, boot file `train.py`
   * input `data_url` = `obs://<bucket>/data/`, output `train_url` = `obs://<bucket>/output/`
   * hyperparameters: `epochs=120`, `trained_where=ModelArts`
   * resource: the smallest CPU flavour
4. When the job finishes, download `anomaly_ae.json` from `output/` (also `anomaly_ae.ckpt` and
   `anomaly_ae.mindir`). Copy it to `backend/models/anomaly_ae.json` and press **Reload model file** on
   System Health. The panel now shows "Trained with mindspore (ModelArts)" and the validation numbers.

Run it locally first if you like: `pip install numpy` (and `mindspore` if available), then
`python ml/modelarts/train.py --data telemetry.csv --out backend/models`.

How it works: an autoencoder 4 → 8 → 2 → 8 → 4 learns to rebuild normal readings (temperature and humidity
per device, and their change since the previous reading). A reading it cannot rebuild (error above the
threshold) raises an `ml_anomaly` alert with detection method `ml-ae`. The threshold is 3 × the 99.9th
percentile of the training error. The script reports the false alarm rate on held-out readings and the
share of sudden jumps it catches. On the starter data: 0.06 % false alarms and 99.3 % of jumps caught.

## 6. Step 4: lab test with the real ESP32 (real numbers)

Test plan (about 40 minutes):

| # | Action | What to look at |
|---|---|---|
| 1 | Leave the board running for 30 min | Delivery %, interval mean / p95, no outages |
| 2 | Switch the Wi-Fi off for 2 min, then on | One outage of about 120 s, the device goes offline then online |
| 3 | Warm the sensor with your hand for 1 min | Anomaly model alert (`ml_anomaly`) or out-of-range alert |
| 4 | Send `quarantine`, then `release` from IoTDA or CyberShield | LED blinks fast, readings stop, then resume |
| 5 | Run it once over local MQTT and once over IoTDA | Compare delivery and interval in the transport row |

Then press **Report** on System Health (period: last 1 h). It downloads `cybershield-lab-report.md` with
the measured numbers. Put that table in the competition documents and show the panel in the demo video.

## 7. Demo video (3 to 5 minutes)

1. Problem in 20 seconds: remote IoT over satellite / 5G, no security team.
2. The 3D twin and the SOC overview.
3. **Demo Scenario**: the attack, the detection, the AI analyst with its citations, your approval, then
   recovery and the report.
4. The real ESP32 on Huawei IoTDA: the IoTDA console, then the LAB readings and lab report in CyberShield.
5. ModelArts: the training job and its log, then the model status in CyberShield.
6. Close with the three new points from section 1.

## 8. Be honest with the judges

Attacks, the satellite / 5G links and quarantine on simulated devices are simulated. The ESP32 readings,
IoTDA, ModelArts training and every dashboard number are real. Say this clearly. Judges trust a project
more when it says what is simulated.
