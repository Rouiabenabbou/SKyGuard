"""
Simulation controls.

GET  /api/simulation/status
POST /api/simulation/start
POST /api/simulation/pause
POST /api/simulation/reset
POST /api/simulation/attack/{attack}   attack = excessive-traffic | unauthorized-device |
                                        abnormal-reading | connection-storm
                                        optional ?device_id=IOT-002
"""
import asyncio

from fastapi import APIRouter, HTTPException

from app.attack_simulator import ATTACKS

from app.simulation_controller import controller

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


@router.get("/status")
def status():
    return controller.status()


@router.post("/start")
async def start():
    return {"message": "Simulation running", **(await controller.start())}


@router.post("/pause")
async def pause():
    return {"message": "Simulation paused", **(await controller.pause())}


@router.post("/reset")
async def reset(restart: bool = True):
    """restart=false wipes everything but leaves the simulation paused (used by the tests)."""
    status = await controller.reset(restart=restart)
    return {"message": "Simulation reset and restarted" if restart else "Simulation reset (paused)", **status}


_running_attacks: set[asyncio.Task] = set()


@router.post("/attack/{attack}")
async def start_attack(attack: str, device_id: str | None = None):
    if attack not in ATTACKS:
        raise HTTPException(status_code=404, detail=f"Unknown attack '{attack}'. Choose one of: {', '.join(ATTACKS)}")
    func, default_device = ATTACKS[attack]
    target = device_id or default_device
    task = asyncio.create_task(func(target, controller.session_id))
    _running_attacks.add(task)  # keep a reference so the task isn't garbage-collected
    task.add_done_callback(_running_attacks.discard)
    return {"message": f"Simulated {attack} attack started", "device_id": target,
            "note": "Simulation inside this project only. Watch the alerts panel."}
