"""FastAPI app: REST endpoints plus the background sim loop."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db
from .sim import World

STATE = {"world": None}


def new_world():
    db.reset_db()
    w = World(live=True)
    w.persist()
    STATE["world"] = w
    return w


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
    return {"kpis": world().kpis(), "fleet_sizing": db.get_meta("fleet_sizing", [])}
