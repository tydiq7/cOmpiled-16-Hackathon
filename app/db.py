"""SQLite schema, seeding and queries. One shared connection (sim loop + API share the process)."""
import json
import math
import sqlite3
import threading

from . import seed_ucsd

DB_PATH = "fleet.db"
lock = threading.RLock()  # hold while doing multi-statement work from the sim loop or API

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (id TEXT PRIMARY KEY, name TEXT, center_lat REAL, center_lng REAL);
CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, site_id TEXT, name TEXT, lat REAL, lng REAL);
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY, site_id TEXT, from_id TEXT, to_id TEXT, length_m REAL,
    blocked INTEGER DEFAULT 0, blocked_until TEXT);
CREATE TABLE IF NOT EXISTS bins (
    id TEXT PRIMARY KEY, site_id TEXT, node_id TEXT, capacity_l REAL, fill_pct REAL DEFAULT 0,
    fill_rate_pct_per_hr REAL, last_emptied_at TEXT, status TEXT DEFAULT 'ok');
CREATE TABLE IF NOT EXISTS docks (id TEXT PRIMARY KEY, site_id TEXT, node_id TEXT, slots INTEGER);
CREATE TABLE IF NOT EXISTS robots (
    id TEXT PRIMARY KEY, site_id TEXT, current_node_id TEXT, state TEXT DEFAULT 'IDLE',
    battery_pct REAL DEFAULT 100, load_pct REAL DEFAULT 0, task_id INTEGER, last_progress_at TEXT,
    lat REAL, lng REAL, route_json TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, bin_id TEXT, robot_id TEXT, created_at TEXT,
    assigned_at TEXT, completed_at TEXT, status TEXT DEFAULT 'open', attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, sim_time TEXT, kind TEXT,
    robot_id TEXT, bin_id TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def _haversine_m(a, b):
    r = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def reset_db():
    """Drop everything and reseed from seed_ucsd. Used at startup and by /sim/reset."""
    with lock:
        c = conn()
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            c.execute(f"DROP TABLE IF EXISTS {t}")
        c.executescript(SCHEMA)
        s = seed_ucsd
        site = s.SITE["id"]
        c.execute("INSERT INTO sites VALUES (?,?,?,?)",
                  (site, s.SITE["name"], s.SITE["center_lat"], s.SITE["center_lng"]))
        nodes = {n["id"]: n for n in s.NODES}
        for n in s.NODES:
            c.execute("INSERT INTO nodes VALUES (?,?,?,?,?)", (n["id"], site, n["name"], n["lat"], n["lng"]))
        for e in s.EDGES:
            length = e.get("length_m") or round(_haversine_m(nodes[e["from"]], nodes[e["to"]]), 1)
            c.execute("INSERT INTO edges (id, site_id, from_id, to_id, length_m) VALUES (?,?,?,?,?)",
                      (e["id"], site, e["from"], e["to"], length))
        for b in s.BINS:
            c.execute("INSERT INTO bins (id, site_id, node_id, capacity_l, fill_rate_pct_per_hr) VALUES (?,?,?,?,?)",
                      (b["id"], site, b["node_id"], b["capacity_l"], b["fill_rate_pct_per_hr"]))
        for d in s.DOCKS:
            c.execute("INSERT INTO docks VALUES (?,?,?,?)", (d["id"], site, d["node_id"], d["slots"]))
        for r in s.ROBOTS:
            n = nodes[r["node_id"]]
            c.execute("INSERT INTO robots (id, site_id, current_node_id, lat, lng) VALUES (?,?,?,?,?)",
                      (r["id"], site, r["node_id"], n["lat"], n["lng"]))
        c.commit()


def add_event(sim_time, kind, message, robot_id=None, bin_id=None, **data):
    """Log an event. `message` is the human-readable line shown in the dashboard feed."""
    with lock:
        c = conn()
        cur = c.execute(
            "INSERT INTO events (ts, sim_time, kind, robot_id, bin_id, data_json) VALUES (datetime('now'),?,?,?,?,?)",
            (sim_time, kind, robot_id, bin_id, json.dumps({"message": message, **data})))
        c.commit()
        return cur.lastrowid


def get_events(since=0, limit=200):
    rows = conn().execute("SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?", (since, limit)).fetchall()
    return [{"id": r["id"], "sim_time": r["sim_time"], "kind": r["kind"], "robot_id": r["robot_id"],
             "bin_id": r["bin_id"], "message": json.loads(r["data_json"]).get("message", "")} for r in rows]


def set_meta(key, value):
    with lock:
        conn().execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))
        conn().commit()


def get_meta(key, default=None):
    row = conn().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def get_state(sim_time, running, speed):
    """Build the Contract 1 snapshot for GET /state."""
    c = conn()
    rows = lambda q: [dict(r) for r in c.execute(q).fetchall()]
    robots = []
    for r in rows("SELECT * FROM robots ORDER BY id"):
        robots.append({"id": r["id"], "lat": r["lat"], "lng": r["lng"], "node_id": r["current_node_id"],
                       "state": r["state"], "battery_pct": round(r["battery_pct"], 1),
                       "load_pct": round(r["load_pct"], 1), "route": json.loads(r["route_json"] or "[]")})
    last_id = c.execute("SELECT MAX(id) FROM events").fetchone()[0] or 0
    return {
        "sim_time": sim_time,
        "running": running,
        "speed": speed,
        "nodes": rows("SELECT id, name, lat, lng FROM nodes"),
        "edges": [{"id": e["id"], "from": e["from_id"], "to": e["to_id"], "length_m": e["length_m"],
                   "blocked": bool(e["blocked"])} for e in rows("SELECT * FROM edges")],
        "bins": [{"id": b["id"], "node_id": b["node_id"], "fill_pct": round(b["fill_pct"], 1),
                  "status": b["status"]} for b in rows("SELECT * FROM bins")],
        "docks": rows("SELECT id, node_id, slots FROM docks"),
        "robots": robots,
        "events": get_events(since=max(0, last_id - 20)),
        "kpis": get_meta("kpis", {"robots_active": 0, "overflow_minutes": 0, "avg_wait_min": 0,
                                  "distance_per_pickup_m": 0}),
        "fleet_sizing": get_meta("fleet_sizing", []),
    }
