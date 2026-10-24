"""SQLite schema, seeding and queries. One shared connection (sim loops + API share the process).

Every venue-owned table is keyed by (site_id, id), so two sites can both have a bin "b1" or a robot
"r1" without touching each other, and every query below is scoped to one site.
"""
import json
import sqlite3
import threading

from . import sites

DB_PATH = "fleet.db"
lock = threading.RLock()  # hold while doing multi-statement work from a sim loop or the API

SCHEMA = """
CREATE TABLE sites (id TEXT PRIMARY KEY, name TEXT, center_lat REAL, center_lng REAL);
CREATE TABLE nodes (site_id TEXT, id TEXT, name TEXT, lat REAL, lng REAL, PRIMARY KEY (site_id, id));
CREATE TABLE edges (
    site_id TEXT, id TEXT, from_id TEXT, to_id TEXT, length_m REAL,
    blocked INTEGER DEFAULT 0, blocked_until TEXT, PRIMARY KEY (site_id, id));
CREATE TABLE bins (
    site_id TEXT, id TEXT, node_id TEXT, capacity_l REAL, fill_pct REAL DEFAULT 0,
    fill_rate_pct_per_hr REAL, last_emptied_at TEXT, status TEXT DEFAULT 'ok', PRIMARY KEY (site_id, id));
CREATE TABLE docks (site_id TEXT, id TEXT, node_id TEXT, slots INTEGER, PRIMARY KEY (site_id, id));
CREATE TABLE robots (
    site_id TEXT, id TEXT, current_node_id TEXT, state TEXT DEFAULT 'IDLE',
    battery_pct REAL DEFAULT 100, load_pct REAL DEFAULT 0, task_id INTEGER, last_progress_at TEXT,
    lat REAL, lng REAL, route_json TEXT DEFAULT '[]', PRIMARY KEY (site_id, id));
CREATE TABLE tasks (
    site_id TEXT, id INTEGER, bin_id TEXT, robot_id TEXT, created_at TEXT,
    assigned_at TEXT, completed_at TEXT, status TEXT DEFAULT 'open', attempts INTEGER DEFAULT 0,
    PRIMARY KEY (site_id, id));
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, site_id TEXT, ts TEXT, sim_time TEXT, kind TEXT,
    robot_id TEXT, bin_id TEXT, data_json TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""
SITE_TABLES = ("nodes", "edges", "bins", "docks", "robots", "tasks", "events")

_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def _seed_site(c, s):
    c.execute("INSERT INTO sites VALUES (?,?,?,?)", (s.id, s.name, s.center_lat, s.center_lng))
    pos = {n["id"]: n for n in s.nodes}
    for n in s.nodes:
        c.execute("INSERT INTO nodes VALUES (?,?,?,?,?)", (s.id, n["id"], n["name"], n["lat"], n["lng"]))
    for e in s.edges:
        c.execute("INSERT INTO edges (site_id, id, from_id, to_id, length_m) VALUES (?,?,?,?,?)",
                  (s.id, e["id"], e["from"], e["to"], e["length_m"]))
    for b in s.bins:
        c.execute("INSERT INTO bins (site_id, id, node_id, capacity_l, fill_rate_pct_per_hr) VALUES (?,?,?,?,?)",
                  (s.id, b["id"], b["node_id"], b["capacity_l"], b["fill_rate_pct_per_hr"]))
    for d in s.docks:
        c.execute("INSERT INTO docks VALUES (?,?,?,?)", (s.id, d["id"], d["node_id"], d["slots"]))
    for r in s.robots:
        n = pos[r["node_id"]]
        c.execute("INSERT INTO robots (site_id, id, current_node_id, lat, lng) VALUES (?,?,?,?,?)",
                  (s.id, r["id"], r["node_id"], n["lat"], n["lng"]))


def reset_db():
    """Drop everything and reseed every registered site. Used at startup."""
    with lock:
        c = conn()
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            c.execute(f"DROP TABLE IF EXISTS {t}")
        c.executescript(SCHEMA)
        for s in sites.SITES.values():
            _seed_site(c, s)
        c.commit()


def reset_site(site_id):
    """Wipe and reseed ONE site; every other site's rows are untouched."""
    with lock:
        c = conn()
        for t in SITE_TABLES:
            c.execute(f"DELETE FROM {t} WHERE site_id=?", (site_id,))
        c.execute("DELETE FROM sites WHERE id=?", (site_id,))
        c.execute("DELETE FROM meta WHERE key LIKE ?", (f"{site_id}:%",))
        _seed_site(c, sites.get(site_id))
        c.commit()


def add_event(site_id, sim_time, kind, message, robot_id=None, bin_id=None, **data):
    """Log an event. `message` is the human-readable line shown in the dashboard feed."""
    with lock:
        c = conn()
        cur = c.execute(
            "INSERT INTO events (site_id, ts, sim_time, kind, robot_id, bin_id, data_json)"
            " VALUES (?,datetime('now'),?,?,?,?,?)",
            (site_id, sim_time, kind, robot_id, bin_id, json.dumps({"message": message, **data})))
        c.commit()
        return cur.lastrowid


def get_events(site_id, since=0, limit=200):
    rows = conn().execute("SELECT * FROM events WHERE site_id=? AND id > ? ORDER BY id LIMIT ?",
                          (site_id, since, limit)).fetchall()
    return [{"id": r["id"], "sim_time": r["sim_time"], "kind": r["kind"], "robot_id": r["robot_id"],
             "bin_id": r["bin_id"], "message": json.loads(r["data_json"]).get("message", "")} for r in rows]


def set_meta(site_id, key, value):
    with lock:
        conn().execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f"{site_id}:{key}", json.dumps(value)))
        conn().commit()


def get_meta(site_id, key, default=None):
    row = conn().execute("SELECT value FROM meta WHERE key=?", (f"{site_id}:{key}",)).fetchone()
    return json.loads(row["value"]) if row else default


def get_state(site_id, sim_time, running, speed):
    """Build the Contract 1 snapshot for one site (plus an additive `site` block)."""
    c = conn()
    rows = lambda q: [dict(r) for r in c.execute(q, (site_id,)).fetchall()]
    robots = []
    for r in rows("SELECT * FROM robots WHERE site_id=? ORDER BY id"):
        robots.append({"id": r["id"], "lat": r["lat"], "lng": r["lng"], "node_id": r["current_node_id"],
                       "state": r["state"], "battery_pct": round(r["battery_pct"], 1),
                       "load_pct": round(r["load_pct"], 1), "route": json.loads(r["route_json"] or "[]")})
    last_id = c.execute("SELECT MAX(id) FROM events WHERE site_id=?", (site_id,)).fetchone()[0] or 0
    s = sites.get(site_id)
    return {
        "site": {"id": s.id, "name": s.name, "center_lat": s.center_lat, "center_lng": s.center_lng},
        "sim_time": sim_time,
        "running": running,
        "speed": speed,
        "nodes": rows("SELECT id, name, lat, lng FROM nodes WHERE site_id=?"),
        "edges": [{"id": e["id"], "from": e["from_id"], "to": e["to_id"], "length_m": e["length_m"],
                   "blocked": bool(e["blocked"])} for e in rows("SELECT * FROM edges WHERE site_id=?")],
        "bins": [{"id": b["id"], "node_id": b["node_id"], "fill_pct": round(b["fill_pct"], 1),
                  "status": b["status"]} for b in rows("SELECT * FROM bins WHERE site_id=?")],
        "docks": rows("SELECT id, node_id, slots FROM docks WHERE site_id=?"),
        "robots": robots,
        "events": get_events(site_id, since=max(0, last_id - 20)),
        "kpis": get_meta(site_id, "kpis", {"robots_active": 0, "overflow_minutes": 0, "avg_wait_min": 0,
                                           "distance_per_pickup_m": 0}),
        "fleet_sizing": get_meta(site_id, "fleet_sizing", []),
    }
