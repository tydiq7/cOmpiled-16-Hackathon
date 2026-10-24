"""FastAPI app: REST endpoints. The sim loop gets started from here once sim.py exists."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db

# Sim clock state lives here until sim.py takes it over.
CLOCK = {"sim_time": "2026-10-24T08:00:00", "running": False, "speed": 20}


@asynccontextmanager
async def lifespan(app):
    db.reset_db()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/state")
def state():
    with db.lock:
        return db.get_state(CLOCK["sim_time"], CLOCK["running"], CLOCK["speed"])


@app.get("/events")
def events(since: int = 0):
    return db.get_events(since)
