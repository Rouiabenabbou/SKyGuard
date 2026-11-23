# Huawei competition: your checklist (v2.5.1)

These steps need your Huawei Cloud account and your board, so only you can do them.
The detailed steps for each are in `docs/HUAWEI_INNOVATION.md` (sections in brackets).
Tick each box and take the screenshot listed. The screenshots are your proof for the judges.

## A. Deploy on Huawei Cloud (about 1 hour) [section 3]
- [ ] ECS: Ubuntu 22.04, 2 vCPU / 4 GB, EIP, security group 22 (your IP) + 80
- [ ] On the server: `curl -fsSL https://get.docker.com | sh`
- [ ] Copy the zip: `scp CyberShield-SatCom-3D-v2.5.1.zip root@<EIP>:/root/`
- [ ] `unzip CyberShield-SatCom-3D-v2.5.1.zip && cd CyberShield-SatCom-3D && cp .env.cloud.example .env`
- [ ] `nano .env`: set POSTGRES_PASSWORD and FRONTEND_ORIGINS=http://<EIP>
- [ ] Optional RDS for PostgreSQL (same VPC): set DATABASE_URL in .env
- [ ] `docker compose up -d --build`, then open http://<EIP> and change the demo passwords
- Screenshots: ECS instance list, RDS instance, the dashboard opened at http://<EIP>

## B. AI analyst on DeepSeek (10 min) [docs/DEEPSEEK_AI.md]
- [ ] platform.deepseek.com: top up a little and create an API key
- [ ] CyberShield, Administration -> AI assistant: paste the key, then **Save and test**
- [ ] Run Demo Scenario and open the AI analyst's explanation
- Screenshots: DeepSeek API keys page, the "Working" test message, an AI explanation with citations

## C. ESP32 through IoTDA (1 hour) [section 4]
- [ ] IoTDA: product (MQTT, JSON), device `ESP32-001`, copy device ID + secret
- [ ] `config.h`: `USE_IOTDA 1`, IOTDA_HOST, device ID, secret, `DHT_TYPE DHT11`, Wi-Fi
- [ ] Set IOTDA_PUSH_TOKEN in .env, then a data forwarding rule (HTTP push) to `http://<EIP>/api/iotda/push?token=<IOTDA_PUSH_TOKEN>`
- Screenshots: IoTDA device "online", the message trace, ESP32-001 shown as LAB in CyberShield

## D. Train the model on ModelArts with MindSpore (1 hour) [section 5]
- [ ] Export normal data: `/api/export/telemetry.csv`
- [ ] OBS bucket with `code/`, `data/`, `output/`; upload `ml/modelarts/train.py` and the CSV
- [ ] ModelArts training job (MindSpore image), then download `anomaly_ae.json` to `backend/models/`
- Screenshots: training job "Completed", the loss in the log, model status in CyberShield

## E. Numbers (10 min, on your PC or the server)
- [ ] Backend running, then: `python tools/benchmark.py --password <admin password>`
- [ ] Put `tools/benchmark_results.md` in the report (the table is ready to paste)

## F. Video and pitch
- [ ] Record your voice over `CyberShield-demo-video.mp4` (or record your own screen while running Demo Scenario)
- [ ] Add 20 seconds of the Huawei console screenshots from A to D
- [ ] Pitch deck: problem, solution, Huawei stack, results table, market, team

Cost: the ECS and RDS cost money per hour. Use the free trial / student credits and **stop or
delete them after recording**.
