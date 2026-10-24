"""FastAPI app: REST endpoints plus the background sim loop."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, optimize
from .sim import World, run_headless

STATE = {"world": None, "sweep": None, "sweeping": False}


def new_world():
    db.reset_db()
    w = World(live=True)
    w.persist()
    if STATE["sweep"]:  # reset_db wipes meta; keep the finished sweep
        db.set_meta("fleet_sizing", STATE["sweep"]["results"])
    STATE["world"] = w
    return w


async def run_sweep():
    """Headless fleet-sizing sweep in a worker thread so the live sim keeps ticking."""
    if STATE["sweeping"]:
        return
    STATE["sweeping"] = True
    try:
        result = await asyncio.to_thread(optimize.fleet_size_sweep, run_headless)
        STATE["sweep"] = result
        with db.lock:
            db.set_meta("fleet_sizing", result["results"])
        w = world()
        with db.lock:
            w.log("fleet_sizing", "Fleet sizing done: recommended fleet is "
                  + (f"{result['recommended']} robots" if result["recommended"] else "larger than 8 robots"))
    finally:
        STATE["sweeping"] = False


async def sim_loop():
    while True:
        w = STATE["world"]
        if w.running:
            with db.lock:
                w.tick()
            await asyncio.sleep(1.0 / max(1, w.speed))
        else:
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app):
    new_world()
    task = asyncio.create_task(sim_loop())
    if os.environ.get("SWEEP_ON_START", "1") == "1":
        asyncio.create_task(run_sweep())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def world():
    return STATE["world"]


class Speed(BaseModel):
    ticks_per_sec: int


class BlockEdge(BaseModel):
    edge_id: str
    minutes: int = 30


class RobotRef(BaseModel):
    robot_id: str


class BinReport(BaseModel):
    fill_pct: float


def _lookup(table, key, label):
    if key not in table:
        raise HTTPException(404, f"unknown {label} {key}")


@app.get("/state")
def state():
    w = world()
    with db.lock:
        return db.get_state(w.sim_time(), w.running, w.speed)


@app.get("/events")
def events(since: int = 0):
    return db.get_events(since)


@app.post("/sim/start")
def sim_start():
    world().running = True
    return {"running": True}


@app.post("/sim/pause")
def sim_pause():
    world().running = False
    return {"running": False}


@app.post("/sim/reset")
def sim_reset():
    speed = world().speed
    with db.lock:
        w = new_world()
    w.speed = speed
    return {"running": False}


@app.post("/sim/speed")
def sim_speed(body: Speed):
    world().speed = max(1, min(body.ticks_per_sec, 200))
    return {"speed": world().speed}


@app.post("/faults/block_edge")
def block_edge(body: BlockEdge):
    w = world()
    _lookup(w.edge_by_id, body.edge_id, "edge")
    with db.lock:
        w.set_edge_blocked(body.edge_id, True, body.minutes)
        w.persist()
    return {"ok": True}


@app.post("/faults/freeze_robot")
def freeze_robot(body: RobotRef):
    w = world()
    _lookup(w.robot_by_id, body.robot_id, "robot")
    with db.lock:
        w.freeze_robot(body.robot_id)
        w.persist()
    return {"ok": True}


@app.post("/faults/drain_battery")
def drain_battery(body: RobotRef):
    w = world()
    _lookup(w.robot_by_id, body.robot_id, "robot")
    with db.lock:
        w.drain_battery(body.robot_id)
        w.persist()
    return {"ok": True}


@app.post("/bins/{bin_id}/report")
def bin_report(bin_id: str, body: BinReport):
    w = world()
    _lookup(w.bin_by_id, bin_id, "bin")
    with db.lock:
        w.report_bin(bin_id, body.fill_pct)
        w.persist()
    return {"ok": True}


@app.get("/analytics")
def analytics():
    sweep = STATE["sweep"] or {}
    return {"kpis": world().kpis(), "fleet_sizing": sweep.get("results", []),
            "recommended_fleet": sweep.get("recommended"), "sweep_running": STATE["sweeping"]}


@app.post("/analytics/run_sweep")
async def analytics_run_sweep():
    """Re-run the fleet-sizing sweep (takes a few seconds)."""
    asyncio.create_task(run_sweep())
    return {"started": True}


@app.post("/supervisor/resume")
def supervisor_resume():
    """A human clears the over-budget pause so dispatching continues."""
    w = world()
    w.dispatch_paused = False
    w.energy_pct = 0.0
    for t in w.tasks:
        t["attempts"] = min(t["attempts"], 1)
    return {"dispatch_paused": False}
