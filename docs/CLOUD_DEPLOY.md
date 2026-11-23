# Run CyberShield SatCom 3D in the cloud (Huawei Cloud) - v1.3

This puts the whole system (dashboard, API, PostgreSQL database, MQTT broker) on one
cloud server with Docker. It was tested with Docker Compose on Linux; the steps below
are for a **Huawei Cloud ECS** server, but any Linux VM works the same way.

Everything inside stays simulated: the satellite, 5G core, handover and quarantine are
software models. The cloud only hosts the software.

```
 Browser ──HTTP 80──►  app  (FastAPI + React dashboard, one container)
                        │  └─ DATABASE_URL ─► db (PostgreSQL 16)  or  Huawei Cloud RDS
 ESP32 ──MQTT 1883───►  mqtt (Mosquitto) ◄─┘
```

## 1. Create the server (Huawei Cloud console)

1. **ECS → Buy ECS**: 2 vCPUs, 4 GB RAM is enough (e.g. general-purpose `s6.large.2`),
   image **Ubuntu 22.04** or **24.04**, 40 GB disk.
2. Give it an **EIP** (public IP) and set a key pair or a strong password.
3. **Security group**, inbound rules:

   | Port | For | Who |
   |---|---|---|
   | 22 (TCP) | SSH | your own IP only |
   | 80 (TCP) | dashboard + API | everyone (or your IP for a demo) |
   | 1883 (TCP) | MQTT for real ESP32 boards | **your IP only**, or don't open it |
   | 8883 (TCP) | secure MQTT (TLS) if you set it up | the boards |

   Port 1883 has no password in the default broker config. Do not open it to the
   whole internet; use secure MQTT (`docs/SECURE_MQTT.md`) for that.

## 2. Install Docker on the server

```bash
ssh root@<EIP>
curl -fsSL https://get.docker.com | sh
docker compose version        # should print v2.x
```

## 3. Copy the project and set the passwords

From your PC (PowerShell), copy the zip and unpack it on the server:

```powershell
scp CyberShield-SatCom-3D-phase12.zip root@<EIP>:/root/
```

```bash
apt-get install -y unzip
unzip CyberShield-SatCom-3D-phase12.zip && cd CyberShield-SatCom-3D
cp .env.cloud.example .env
nano .env       # set POSTGRES_PASSWORD (long, random) and FRONTEND_ORIGINS=http://<EIP>
```

## 4. Start it

```bash
docker compose up -d --build      # first build takes a few minutes
docker compose ps                 # db "healthy", app and mqtt "running"
curl http://localhost/api/health  # {"status":"ok",...}
```

Open `http://<EIP>` in a browser and log in (`admin` / `Admin@2026`), then
**change every demo password at once** in Admin → Users.

Useful commands:

```bash
docker compose logs -f app        # live logs
docker compose restart app        # restart after changing .env
docker compose down               # stop (data stays in the pgdata volume)
docker compose up -d --build      # update after copying a new version
```

## 5. Optional: Huawei Cloud RDS for PostgreSQL

To keep the data in a managed database (automatic backups, scaling) instead of the
`db` container:

1. **RDS → Buy DB instance**: PostgreSQL 14 or newer, same VPC as the ECS.
2. Create a database `cybershield` and a user.
3. In `.env`: `DATABASE_URL=postgresql://user:password@<rds-private-ip>:5432/cybershield`
4. `docker compose up -d app` (the `db` container can then be stopped).

The tables are created on the first start. Tests also pass on PostgreSQL
(`TEST_DATABASE_URL=... python -m pytest`).

## 6. Optional: HTTPS and a domain name

For a public demo, put HTTPS in front: a Huawei Cloud **ELB** with a certificate
(from Huawei Cloud SSL Certificate Manager), forwarding to port 80 of the ECS, or
Caddy/Nginx on the server. Then set `FRONTEND_ORIGINS=https://your-domain`.

## 7. Big data on the server

In the dashboard, **Analytics → Long-term history → Generate history** fills the
database with months of simulated readings (90 days × 5 min × 7 devices ≈ 180,000
rows in a few seconds). The backend keeps summarising live readings into hourly
tables every 5 minutes (`ROLLUP_INTERVAL_SECONDS`), so the charts stay fast even
with millions of rows.

## 8. Monitoring (optional)

Set `METRICS_TOKEN=<long random text>` in `.env` and restart. Prometheus, Grafana or Huawei Cloud
AOM can then read `http://<EIP>/metrics` with the header `Authorization: Bearer <token>`.
The Engineering tab shows the same facts (database, size, uptime) in the dashboard.

## 9. Free AI through OmniRoute (optional)

If you run OmniRoute on the same server, set Admin → AI assistant → OmniRoute, address
`http://host.docker.internal:20128/v1` (from inside the app container `localhost` is the container itself;
on Linux add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `app` service).

## 10. Optional: cloud MQTT broker (v2.4)

Instead of the `mqtt` container, use a managed broker like HiveMQ Cloud or EMQX Cloud
(free plans, TLS on 8883). Then port 1883 does not need to be opened at all. See
`docs/CLOUD_MQTT.md`.

## What was tested and what was not

* Tested: the Docker image builds, `docker compose up` starts PostgreSQL, Mosquitto
  and the app; health check, dashboard, MQTT connection and all 104 tests on PostgreSQL.
* Not tested: a real Huawei Cloud account (ECS, RDS, ELB). The steps follow the
  standard console flow; names of instance types can change.
