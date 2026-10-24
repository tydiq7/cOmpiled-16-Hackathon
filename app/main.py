"""FastAPI app: REST endpoints plus one background sim loop per site.

Every endpoint exists twice: /sites/{site_id}/<path> for any venue, and the plain /<path> which
is an alias for the default site (the original dashboard keeps working unchanged).
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, optimize, sites
from .sim import World, run_headless

DEFAULT = sites.DEFAULT_SITE_ID
STATE = {"worlds": {}, "sweeps": {}, "sweeping": set()}


def new_world(site_id):
    """(Re)build one site's world and database rows. Other sites are untouched."""
    with db.lock:
        db.reset_site(site_id)
        w = World(site=sites.get(site_id), live=True)
        w.persist()
        if STATE["sweeps"].get(site_id):  # reset wipes meta; keep a finished sweep
            db.set_meta(site_id, "fleet_sizing", STATE["sweeps"][site_id]["results"])
        STATE["worlds"][site_id] = w
    return w


SWEEP_SEEDS = int(os.environ.get("SWEEP_SEEDS", "5"))   # simulated days per fleet size
SWEEP_REQUIRED_SHARE = 0.8                               # recommend the smallest fleet that meets the target on this share of days


def _sweep(site):
    """Multi-seed fleet-sizing study, shaped into Contract 1 `fleet_sizing` rows (extra fields ride along)."""
    run = lambda n, seed: run_headless(n, seed, site=site)
    study = optimize.fleet_size_study(run, seeds=range(SWEEP_SEEDS), required_share=SWEEP_REQUIRED_SHARE)
    rows = [{"robots": r["robots"], "avg_wait_min": round(r["avg_wait_min"], 1),
             "max_wait_min": round(r["max_wait_p95"], 1), "overflow_minutes": round(r["overflow_minutes"], 1),
             "avg_wait_ci95": round(r["avg_wait_ci95"], 1), "share_meeting_target": round(r["share_meeting_target"], 2),
             "n_seeds": r["n_seeds"]} for r in study["results"]]
    return {"results": rows, "recommended": study["recommended"]}


async def run_sweep(site_id):
    """Headless fleet-sizing sweep in a worker thread so live sims keep ticking."""
    if site_id in STATE["sweeping"]:
        return
    STATE["sweeping"].add(site_id)
    try:
        site = sites.get(site_id)
        result = await asyncio.to_thread(_sweep, site)
        STATE["sweeps"][site_id] = result
        with db.lock:
            db.set_meta(site_id, "fleet_sizing", result["results"])
            STATE["worlds"][site_id].log(
                "fleet_sizing", "Fleet sizing done: recommended fleet is "
                + (f"{result['recommended']} robots" if result["recommended"] else "larger than 8 robots"))
    finally:
        STATE["sweeping"].discard(site_id)


async def sim_loop(site_id):
    while True:
        w = STATE["worlds"][site_id]
        if w.running:
            with db.lock:
                w.tick()
            await asyncio.sleep(1.0 / max(1, w.speed))
        else:
            await asyncio.sleep(0.1)


async def sweep_all():
    for site_id in sites.SITES:
        await run_sweep(site_id)


@asynccontextmanager
async def lifespan(app):
    db.reset_db()
    for site_id in sites.SITES:
        new_world(site_id)
    loops = [asyncio.create_task(sim_loop(sid)) for sid in sites.SITES]
    if os.environ.get("SWEEP_ON_START", "1") == "1":
        loops.append(asyncio.create_task(sweep_all()))
    yield
    for t in loops:
        t.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def world(site_id):
    if site_id not in STATE["worlds"]:
        raise HTTPException(404, f"unknown site {site_id}")
    return STATE["worlds"][site_id]


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


def both(method, path):
    """Register a handler at /sites/{site_id}<path> and at the default-site alias <path>."""
    def deco(fn):
        getattr(app, method)(f"/sites/{{site_id}}{path}")(fn)
        getattr(app, method)(path)(fn)
        return fn
    return deco


# ---- venues -----------------------------------------------------------------------------------
@app.get("/sites")
def list_sites():
    """Every registered venue with its own live numbers: proof each runs independently."""
    out = []
    for sid, s in sites.SITES.items():
        w = STATE["worlds"][sid]
        out.append({"id": sid, "name": s.name, "bins": len(w.bins), "robots": len(w.robots),
                    "nodes": len(w.nodes), "running": w.running, "sim_time": w.sim_time(), "kpis": w.kpis()})
    return out


# ---- per-site endpoints -----------------------------------------------------------------------
@both("get", "/state")
def state(site_id: str = DEFAULT):
    w = world(site_id)
    with db.lock:
        return db.get_state(site_id, w.sim_time(), w.running, w.speed)


@both("get", "/events")
def events(since: int = 0, site_id: str = DEFAULT):
    world(site_id)
    return db.get_events(site_id, since)


@both("post", "/sim/start")
def sim_start(site_id: str = DEFAULT):
    world(site_id).running = True
    return {"running": True}


@both("post", "/sim/pause")
def sim_pause(site_id: str = DEFAULT):
    world(site_id).running = False
    return {"running": False}


@both("post", "/sim/reset")
def sim_reset(site_id: str = DEFAULT):
    speed = world(site_id).speed
    w = new_world(site_id)
    w.speed = speed
    return {"running": False}


@both("post", "/sim/speed")
def sim_speed(body: Speed, site_id: str = DEFAULT):
    w = world(site_id)
    w.speed = max(1, min(body.ticks_per_sec, 200))
    return {"speed": w.speed}


@both("post", "/faults/block_edge")
def block_edge(body: BlockEdge, site_id: str = DEFAULT):
    w = world(site_id)
    _lookup(w.edge_by_id, body.edge_id, "edge")
    with db.lock:
        w.set_edge_blocked(body.edge_id, True, body.minutes)
        w.persist()
    return {"ok": True}


@both("post", "/faults/freeze_robot")
def freeze_robot(body: RobotRef, site_id: str = DEFAULT):
    w = world(site_id)
    _lookup(w.robot_by_id, body.robot_id, "robot")
    with db.lock:
        w.freeze_robot(body.robot_id)
        w.persist()
    return {"ok": True}


@both("post", "/faults/drain_battery")
def drain_battery(body: RobotRef, site_id: str = DEFAULT):
    w = world(site_id)
    _lookup(w.robot_by_id, body.robot_id, "robot")
    with db.lock:
        w.drain_battery(body.robot_id)
        w.persist()
    return {"ok": True}


@both("post", "/bins/{bin_id}/report")
def bin_report(bin_id: str, body: BinReport, site_id: str = DEFAULT):
    w = world(site_id)
    _lookup(w.bin_by_id, bin_id, "bin")
    with db.lock:
        w.report_bin(bin_id, body.fill_pct)
        w.persist()
    return {"ok": True}


@both("get", "/analytics")
def analytics(site_id: str = DEFAULT):
    sweep = STATE["sweeps"].get(site_id) or {}
    return {"kpis": world(site_id).kpis(), "fleet_sizing": sweep.get("results", []),
            "recommended_fleet": sweep.get("recommended"), "sweep_running": site_id in STATE["sweeping"]}


@both("post", "/analytics/run_sweep")
async def analytics_run_sweep(site_id: str = DEFAULT):
    """Re-run the fleet-sizing sweep (takes a few seconds)."""
    world(site_id)
    asyncio.create_task(run_sweep(site_id))
    return {"started": True}


@both("post", "/supervisor/resume")
def supervisor_resume(site_id: str = DEFAULT):
    """A human clears the over-budget pause so dispatching continues."""
    w = world(site_id)
    w.dispatch_paused = False
    w.energy_pct = 0.0
    for t in w.tasks:
        t["attempts"] = min(t["attempts"], 1)
    return {"dispatch_paused": False}
