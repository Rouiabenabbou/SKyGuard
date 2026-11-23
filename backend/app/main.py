"""
Entry point of the CyberShield SatCom 3D backend.

Run from the backend/ folder:
    uvicorn app.main:app --reload
"""
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.database import SessionLocal, init_db
from app.mqtt_client import mqtt_service
from app.detection_engine import detector
from app.quarantine_service import quarantine
from app import auth
from app.routes import ai as ai_routes, auth as auth_routes, companies as companies_routes, notify as notify_routes, analytics as analytics_routes, engineering as engineering_routes, incidents as incidents_routes, graph as graph_routes, soc as soc_routes, hunt as hunt_routes, intel as intel_routes, response as response_routes, iotda as iotda_routes, lab as lab_routes
from app.routes import alerts, devices, failover as failover_routes, ml as ml_routes, network, quarantine as quarantine_routes, reports, simulation, system, timeline as timeline_routes
from app.failover_service import failover
from app.simulation_controller import controller
from app.websocket_manager import manager


async def heartbeat_loop() -> None:
    """Push a small 'heartbeat' message to every browser every few seconds.

    This proves real-time server -> browser messaging works. Later phases
    reuse the same channel for telemetry, alerts and network events.
    """
    counter = 0
    while True:
        await asyncio.sleep(config.HEARTBEAT_INTERVAL)
        counter += 1
        await manager.broadcast(
            "heartbeat",
            {
                "seq": counter,
                "time": datetime.now(timezone.utc).isoformat(),
                "clients": manager.client_count,
            },
        )


async def rollup_loop() -> None:
    """v1.3: summarise the live readings into the long-term hourly tables every few minutes."""
    from app import warehouse
    from app.database import SessionLocal

    while True:
        await asyncio.sleep(config.ROLLUP_INTERVAL_SECONDS)
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(warehouse.rollup_live, db)
        except Exception as exc:
            print(f"[rollup] skipped: {exc}")


async def security_loop() -> None:
    """v2.1: one MQTT flow record per active device per minute; hourly clean-up of old security events."""
    from app import security_events

    ticks = 0
    while True:
        await asyncio.sleep(config.FLOW_SUMMARY_SECONDS)
        ticks += 1
        try:
            with SessionLocal() as db:
                await security_events.flush_flows(db)
                if ticks % max(1, int(3600 / config.FLOW_SUMMARY_SECONDS)) == 0:
                    security_events.purge_old(db)
        except Exception as exc:
            print(f"[security-events] skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code before `yield` runs at startup, code after it runs at shutdown.
    init_db()  # creates database/cybershield.db and the tables on first run
    task = asyncio.create_task(heartbeat_loop())
    rollup_task = asyncio.create_task(rollup_loop())
    security_task = asyncio.create_task(security_loop())
    mqtt_service.session_id_provider = lambda: controller.session_id
    detector.session_id_provider = lambda: controller.session_id
    quarantine.session_id_provider = lambda: controller.session_id
    failover.session_id_provider = lambda: controller.session_id
    mqtt_service.start()  # background connect; app works even if the broker is down
    controller.launch()
    try:  # v1.4: three bigger demo customers, once per database
        from app.big_companies import seed_big_companies
        with SessionLocal() as db:
            added = await seed_big_companies(db)
        if added:
            print(f"[startup] added demo devices: {', '.join(added)}")
    except Exception as exc:
        print(f"[startup] big companies skipped: {exc}")
    try:  # v1.5: second satellite, more towers and 16 more devices, once per database
        from app.network_expansion import seed_network_v15
        with SessionLocal() as db:
            added = await seed_network_v15(db)
        if added:
            print(f"[startup] v1.5 network: added {len(added)} devices")
    except Exception as exc:
        print(f"[startup] v1.5 network skipped: {exc}")
    try:  # v2.1: demo IOCs, SOC analyst accounts, audit hash chain
        from app import intel, soc_access
        with SessionLocal() as db:
            intel.seed_demo_iocs(db)
            soc_access.seed_soc_users(db)
            auth.chain_pending(db)
    except Exception as exc:
        print(f"[startup] v2.1 seed skipped: {exc}")
    if config.SIM_AUTOSTART:
        await controller.start()
    print(f"[startup] {config.APP_NAME} v{config.APP_VERSION} ready")
    yield
    controller.shutdown()
    mqtt_service.stop()
    task.cancel()
    rollup_task.cancel()
    security_task.cancel()
    print("[shutdown] backend stopped")


app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description="Digital twin backend for a simulated satellite-5G IoT network.",
    lifespan=lifespan,
)

# v1.1: every /api request is checked against the user's role and changes are audited.
# (Added before CORS, so CORS stays the outer layer and error replies still carry CORS headers.)
app.middleware("http")(auth.auth_middleware)

# Allow the React dev server (another port) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(devices.router)
app.include_router(simulation.router)
app.include_router(network.router)
app.include_router(alerts.router)
app.include_router(quarantine_routes.router)
app.include_router(failover_routes.router)
app.include_router(timeline_routes.router)
app.include_router(reports.router)
app.include_router(ml_routes.router)
app.include_router(auth_routes.router)
app.include_router(ai_routes.router)
app.include_router(companies_routes.router)
app.include_router(notify_routes.router)
app.include_router(analytics_routes.router)
app.include_router(engineering_routes.router)
app.include_router(incidents_routes.router)
app.include_router(graph_routes.router)
app.include_router(soc_routes.router)
app.include_router(hunt_routes.router)
app.include_router(intel_routes.router)
app.include_router(response_routes.router)
app.include_router(iotda_routes.router)
app.include_router(lab_routes.router)


@app.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    """v1.4 (cloud): Prometheus metrics, only when METRICS_TOKEN is set and sent as a Bearer token."""
    import hmac

    if not config.METRICS_TOKEN:
        raise HTTPException(status_code=404, detail="Metrics are off (set METRICS_TOKEN).")
    sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(sent, config.METRICS_TOKEN):
        raise HTTPException(status_code=401, detail="Bad metrics token.")
    from app.routes.engineering import metrics_text
    with SessionLocal() as db:
        return PlainTextResponse(metrics_text(db), media_type="text/plain; version=0.0.4")


# v1.3 (cloud): serve the built dashboard from the same server, so one address
# (e.g. http://<Huawei ECS IP>) gives the dashboard, the API and the WebSocket.
_INDEX = config.FRONTEND_DIST / "index.html"


@app.get("/", include_in_schema=False)
def root():
    if _INDEX.exists():
        return FileResponse(_INDEX)
    return {"message": f"{config.APP_NAME} backend is running. See /docs for the API."}


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Files of the built dashboard (JS, CSS, textures); any other page gets index.html."""
    if path.startswith(("api/", "ws", "docs", "openapi.json", "redoc")) or not _INDEX.exists():
        raise HTTPException(status_code=404, detail="Not found")
    file = (config.FRONTEND_DIST / path).resolve()
    if file.is_file() and config.FRONTEND_DIST.resolve() in file.parents:
        return FileResponse(file)
    return FileResponse(_INDEX)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Live channel to the dashboard.

    The server sends JSON messages shaped like {"type": ..., "data": ...}.
    The browser may send {"type": "ping", "sent_at": <ms>} and gets a "pong"
    back, which the dashboard uses to measure round-trip latency.
    """
    company_id = None
    if config.AUTH_ENABLED:  # v1.1: the live channel needs a login token too (?token=...)
        from app import tenancy
        from app.database import SessionLocal
        with SessionLocal() as db:
            user = auth.user_for_token(db, auth.token_from(websocket))
            if user is None:
                await websocket.close(code=4401)
                return
            company_id = tenancy.company_id_of_user(db, user.username)  # v1.2: company users get filtered messages
    await manager.connect(websocket, company_id)
    await manager.send(websocket, "welcome", {"message": "Connected to CyberShield backend"})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await manager.send(
                    websocket,
                    "pong",
                    {"sent_at": message.get("sent_at"), "server_time": time.time() * 1000},
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # bad JSON etc. - log and drop the client
        print(f"[ws] client error: {exc}")
    finally:
        manager.disconnect(websocket)
