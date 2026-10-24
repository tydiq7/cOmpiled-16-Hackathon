"""The simulated world: bins filling, robots moving, faults. One tick = one sim-minute.

World is the in-memory source of truth. In live mode it mirrors itself into SQLite every tick
(so /state and the event log read from the shared database); headless mode (fleet-sizing sweep)
skips the database entirely and runs as fast as Python allows.
"""
import json
import random
from datetime import datetime, timedelta

from . import db, dispatcher, navigation as nav, seed_ucsd

DAY_START = datetime(2026, 10, 24, 8, 0)
DAY_END_MIN = 12 * 60  # 8 AM -> 8 PM


def fill_multiplier(hour):
    """Time-of-day curve applied to each bin's base fill rate (busy at lunch and between classes)."""
    if hour < 7:
        return 0.1
    if hour < 10:
        return 0.7
    if hour < 11:
        return 1.2
    if hour < 14:
        return 2.4  # lunch rush
    if hour < 17:
        return 1.2
    return 0.5


class World:
    SPEED_M_PER_MIN = 80.0       # ~1.3 m/s walking pace
    ROBOT_CAPACITY_L = 400.0
    DRAIN_PER_M = 0.012          # battery % per metre driven
    IDLE_DRAIN_PER_MIN = 0.005
    CHARGE_PER_MIN = 3.0
    LOW_BATTERY_PCT = 25.0
    COLLECT_MIN = 2
    UNLOAD_MIN = 3

    def __init__(self, num_robots=None, seed=42, live=False):
        self.live = live
        self.rng = random.Random(seed)
        self.t = 0                    # sim minutes since DAY_START
        self.running = False
        self.speed = 20               # ticks per real second
        self.events = []              # in-memory log (headless) -- live mode writes to SQLite
        self._event_id = 0

        s = seed_ucsd
        self.nodes = {n["id"]: dict(n) for n in s.NODES}
        self.edges = []
        for e in s.EDGES:
            a, b = self.nodes[e["from"]], self.nodes[e["to"]]
            length = e.get("length_m") or round(db._haversine_m(a, b), 1)
            self.edges.append({"id": e["id"], "from": e["from"], "to": e["to"], "length_m": length,
                               "blocked": False, "blocked_until": None,
                               "name": e.get("name") or f"{a['name']}-{b['name']}"})
        self.edge_by_id = {e["id"]: e for e in self.edges}
        self.graph = nav.build_graph(self.nodes.values(), self.edges)

        self.bins = [{"id": b["id"], "node_id": b["node_id"], "capacity_l": b["capacity_l"],
                      "rate": b["fill_rate_pct_per_hr"], "fill_pct": self.rng.uniform(5, 40),
                      "status": "ok", "last_emptied": None} for b in s.BINS]
        self.bin_by_id = {b["id"]: b for b in self.bins}
        self.docks = [dict(d) for d in s.DOCKS]

        robot_seed = list(s.ROBOTS)
        if num_robots is not None:  # headless sweeps: n robots spread over the docks
            robot_seed = [{"id": f"r{i + 1}", "node_id": self.docks[i % len(self.docks)]["node_id"]}
                          for i in range(num_robots)]
        self.robots = [self._new_robot(r) for r in robot_seed]
        self.robot_by_id = {r["id"]: r for r in self.robots}

        self.tasks = []
        self._task_id = 0
        # metrics
        self.overflow_minutes = 0
        self.waits = []               # minutes from 80% full to emptied, per completed pickup
        self.dist_driven_m = 0.0
        self.pickups = 0

    # ---- construction helpers -------------------------------------------------------------
    def _new_robot(self, r):
        n = self.nodes[r["node_id"]]
        return {"id": r["id"], "node": r["node_id"], "state": "IDLE", "battery": 100.0, "load": 0.0,
                "lat": n["lat"], "lng": n["lng"], "route": [], "path": [], "seg": None,
                "task_id": None, "timer": 0, "frozen": False, "waiting": False,
                "drain_mult": 1.0, "drain_until": None, "last_progress": 0, "target": None}

    def new_task(self, b):
        self._task_id += 1
        t = {"id": self._task_id, "bin_id": b["id"], "robot_id": None, "created": self.t,
             "assigned": None, "completed": None, "status": "open", "attempts": 0}
        self.tasks.append(t)
        self._refresh_bin_status(b)
        return t

    # ---- small queries --------------------------------------------------------------------
    def sim_time(self, minutes=None):
        return (DAY_START + timedelta(minutes=self.t if minutes is None else minutes)).isoformat()

    def node_name(self, node_id):
        return self.nodes[node_id]["name"]

    def edge_between(self, u, v):
        return self.edge_by_id[self.graph[u][v]["id"]]

    def bin_demand_pct(self, b):
        """Percent of a robot's capacity this bin will fill."""
        return min(b["fill_pct"], 100.0) / 100.0 * b["capacity_l"] / self.ROBOT_CAPACITY_L * 100.0

    def nearest_dock(self, node_id):
        """(dock_node_id, distance_m) of the closest reachable dock, or None."""
        best = None
        for d in self.docks:
            p = nav.shortest_path(self.graph, node_id, d["node_id"])
            if p and (best is None or p[1] < best[1]):
                best = (d["node_id"], p[1])
        return best

    def log(self, kind, message, robot_id=None, bin_id=None):
        if self.live:
            db.add_event(self.sim_time(), kind, message, robot_id=robot_id, bin_id=bin_id)
        else:
            self._event_id += 1
            self.events.append({"id": self._event_id, "sim_time": self.sim_time(), "kind": kind,
                                "message": message, "robot_id": robot_id, "bin_id": bin_id})

    # ---- dispatcher hooks -----------------------------------------------------------------
    def assign(self, task, robot, bin_ids):
        task["status"], task["robot_id"], task["assigned"] = "assigned", robot["id"], self.t
        task["attempts"] += 1
        robot["route"] = list(bin_ids)
        robot["task_id"] = task["id"]
        robot["last_progress"] = self.t
        self._refresh_bin_status(self.bin_by_id[task["bin_id"]])

    def _refresh_bin_status(self, b):
        if b["fill_pct"] >= 100:
            b["status"] = "overflowing"
        elif any(t["bin_id"] == b["id"] and t["status"] == "assigned" for t in self.tasks):
            b["status"] = "assigned"
        elif any(t["bin_id"] == b["id"] and t["status"] in ("open", "escalated") for t in self.tasks):
            b["status"] = "needs_pickup"
        else:
            b["status"] = "ok"

    # ---- movement -------------------------------------------------------------------------
    def _begin_path(self, r, dst_node):
        """Point the robot at dst_node. Returns False if no unblocked route exists."""
        p = nav.shortest_path(self.graph, r["node"], dst_node)
        if p is None:
            return False
        r["path"], r["target"], r["waiting"] = p[0][1:], dst_node, False
        return True

    def _replan(self, r, blocked_name=None):
        """Recompute the path from where the robot will next be at a node."""
        origin = r["seg"][1] if r["seg"] else r["node"]
        p = nav.shortest_path(self.graph, origin, r["target"])
        if p is None:
            if not r["waiting"]:
                self.log("no_route", f"Robot {r['id']} has no route to {self.node_name(r['target'])}: waiting",
                         robot_id=r["id"])
            r["waiting"] = True
            return False
        r["path"] = ([origin] if r["seg"] else []) + p[0][1:]
        if blocked_name:
            self.log("reroute", f"Robot {r['id']} rerouted: {blocked_name} blocked", robot_id=r["id"])
        r["waiting"] = False
        return True

    def _first_blocked_edge(self, r):
        nodes = ([r["seg"][1]] if r["seg"] else [r["node"]]) + (r["path"][1:] if r["seg"] else r["path"])
        for a, b in zip(nodes, nodes[1:]):
            if self.graph[a][b]["blocked"]:
                return self.edge_between(a, b)
        return None

    def _advance(self, r):
        """Move up to one tick of distance along the path. Returns True once the path is finished."""
        if r["battery"] <= 0:
            return False
        blocked = self._first_blocked_edge(r)
        if blocked or r["waiting"]:
            if not self._replan(r, blocked["name"] if blocked else None):
                return False
        budget, moved = self.SPEED_M_PER_MIN, False
        while budget > 1e-9:
            if r["seg"]:
                u, v, pos, length = r["seg"]
                step = min(budget, length - pos)
                pos, budget, moved = pos + step, budget - step, True
                self.dist_driven_m += step
                r["battery"] -= step * self.DRAIN_PER_M * r["drain_mult"]
                if pos >= length - 1e-9:
                    r["node"], r["seg"] = v, None
                    r["path"].pop(0)
                    n = self.nodes[v]
                    r["lat"], r["lng"] = n["lat"], n["lng"]
                else:
                    r["seg"] = (u, v, pos, length)
                    a, b, f = self.nodes[u], self.nodes[v], pos / length
                    r["lat"], r["lng"] = a["lat"] + (b["lat"] - a["lat"]) * f, a["lng"] + (b["lng"] - a["lng"]) * f
            else:
                if not r["path"]:
                    break
                nxt = r["path"][0]
                e = self.edge_between(r["node"], nxt)
                r["seg"] = (r["node"], nxt, 0.0, e["length_m"])
        if moved:
            r["last_progress"] = self.t
        return not r["seg"] and not r["path"]

    # ---- robot state machine (movement side; the supervisor watches for trouble) ----------
    def _step_robot(self, r):
        if r["drain_until"] is not None and self.t >= r["drain_until"]:
            r["drain_mult"], r["drain_until"] = 1.0, None
        r["battery"] = max(0.0, r["battery"] - self.IDLE_DRAIN_PER_MIN * r["drain_mult"])
        if r["frozen"]:
            return
        st = r["state"]
        if st == "IDLE":
            if r["route"]:
                b = self.bin_by_id[r["route"][0]]
                if self._begin_path(r, b["node_id"]):
                    r["state"], r["last_progress"] = "EN_ROUTE", self.t
                    self._advance_and_arrive(r)
                else:
                    self._release_task(r, "no route to bin")
            else:
                r["last_progress"] = self.t  # idle robots are not "stuck"
        elif st == "EN_ROUTE" or st == "RETURNING":
            self._advance_and_arrive(r)
        elif st == "COLLECTING":
            r["timer"] -= 1
            r["last_progress"] = self.t
            if r["timer"] <= 0:
                self._finish_collect(r)
        elif st == "UNLOADING":
            r["timer"] -= 1
            r["last_progress"] = self.t
            if r["timer"] <= 0:
                r["load"] = 0.0
                r["state"] = "CHARGING" if r["battery"] < 90 else "IDLE"
                self.log("unload", f"Robot {r['id']} unloaded at dock {self.node_name(r['node'])}", robot_id=r["id"])
        elif st == "CHARGING":
            r["last_progress"] = self.t
            r["battery"] = min(100.0, r["battery"] + self.CHARGE_PER_MIN)
            if r["battery"] >= 95:
                r["state"] = "IDLE"

    def _advance_and_arrive(self, r):
        if not self._advance(r):
            return
        if r["state"] == "EN_ROUTE":
            r["state"], r["timer"] = "COLLECTING", self.COLLECT_MIN
        elif r["state"] == "RETURNING":
            r["state"], r["timer"] = "UNLOADING", self.UNLOAD_MIN

    def _finish_collect(self, r):
        b = self.bin_by_id[r["route"].pop(0)]
        r["load"] = min(100.0, r["load"] + self.bin_demand_pct(b))
        task = next((t for t in self.tasks if t["bin_id"] == b["id"] and t["status"] == "assigned"), None)
        if task:
            task["status"], task["completed"] = "done", self.t
            self.waits.append(self.t - task["created"])
            self.pickups += 1
        was = b["fill_pct"]
        b["fill_pct"], b["last_emptied"] = 0.0, self.t
        self._refresh_bin_status(b)
        self.log("collected", f"Robot {r['id']} emptied bin {b['id']} at {self.node_name(b['node_id'])} "
                              f"({was:.0f}% full)", robot_id=r["id"], bin_id=b["id"])
        r["task_id"] = None
        if r["route"]:
            if self._begin_path(r, self.bin_by_id[r["route"][0]]["node_id"]):
                r["state"] = "EN_ROUTE"
                return
        dock = self.nearest_dock(r["node"])
        if dock and self._begin_path(r, dock[0]):
            r["state"] = "RETURNING"
        else:
            r["state"] = "IDLE"

    def _release_task(self, r, why):
        for bid in r["route"]:
            for t in self.tasks:
                if t["bin_id"] == bid and t["status"] == "assigned":
                    t["status"], t["robot_id"] = "open", None
                    self._refresh_bin_status(self.bin_by_id[bid])
        r["route"], r["task_id"] = [], None
        self.log("task_released", f"Robot {r['id']} released its task ({why})", robot_id=r["id"])

    # ---- tick -----------------------------------------------------------------------------
    def tick(self):
        self.t += 1
        hour = (DAY_START + timedelta(minutes=self.t)).hour
        mult = fill_multiplier(hour)
        for e in self.edges:  # crowds disperse
            if e["blocked"] and e["blocked_until"] is not None and self.t >= e["blocked_until"]:
                self.set_edge_blocked(e["id"], False)
        for b in self.bins:
            b["fill_pct"] += b["rate"] / 60.0 * mult * self.rng.uniform(0.7, 1.3)
            if b["fill_pct"] >= 100:
                self.overflow_minutes += 1
            self._refresh_bin_status(b)
        dispatcher.step(self)
        for r in self.robots:
            self._step_robot(r)
        if self.live:
            self.persist()

    # ---- faults ---------------------------------------------------------------------------
    def set_edge_blocked(self, edge_id, blocked, minutes=None):
        e = self.edge_by_id[edge_id]
        e["blocked"] = blocked
        e["blocked_until"] = (self.t + minutes) if (blocked and minutes) else None
        nav.set_blocked(self.graph, e["from"], e["to"], blocked)
        if blocked:
            self.log("edge_blocked", f"Crowd blocking {e['name']}" + (f" for {minutes} min" if minutes else ""))
        else:
            self.log("edge_cleared", f"{e['name']} is clear again")

    def freeze_robot(self, robot_id):
        r = self.robot_by_id[robot_id]
        r["frozen"] = True
        self.log("fault", f"FAULT: Robot {robot_id} frozen", robot_id=robot_id)

    def drain_battery(self, robot_id, minutes=15, mult=12.0):
        r = self.robot_by_id[robot_id]
        r["drain_mult"], r["drain_until"] = mult, self.t + minutes
        self.log("fault", f"FAULT: Robot {robot_id} battery draining fast", robot_id=robot_id)

    def report_bin(self, bin_id, fill_pct):
        b = self.bin_by_id[bin_id]
        b["fill_pct"] = max(0.0, float(fill_pct))
        self._refresh_bin_status(b)

    # ---- metrics --------------------------------------------------------------------------
    def kpis(self):
        waits = self.waits or [0]
        return {"robots_active": sum(1 for r in self.robots if r["state"] not in ("IDLE", "CHARGING")),
                "overflow_minutes": self.overflow_minutes,
                "avg_wait_min": round(sum(waits) / len(waits), 1),
                "distance_per_pickup_m": round(self.dist_driven_m / self.pickups) if self.pickups else 0}

    def final_waits(self):
        """Waits of finished pickups plus the running wait of tasks still open (so a tiny fleet can't hide)."""
        pending = [self.t - t["created"] for t in self.tasks if t["status"] in ("open", "assigned", "escalated")]
        return self.waits + pending

    # ---- persistence ----------------------------------------------------------------------
    def persist(self):
        with db.lock:
            c = db.conn()
            c.executemany("UPDATE bins SET fill_pct=?, status=?, last_emptied_at=? WHERE id=?",
                          [(b["fill_pct"], b["status"], b["last_emptied"] and self.sim_time(b["last_emptied"]), b["id"])
                           for b in self.bins])
            c.executemany(
                "UPDATE robots SET current_node_id=?, state=?, battery_pct=?, load_pct=?, task_id=?,"
                " last_progress_at=?, lat=?, lng=?, route_json=? WHERE id=?",
                [(r["node"], r["state"], r["battery"], r["load"], r["task_id"], self.sim_time(r["last_progress"]),
                  r["lat"], r["lng"], json.dumps(r["route"]), r["id"]) for r in self.robots])
            c.executemany("UPDATE edges SET blocked=?, blocked_until=? WHERE id=?",
                          [(int(e["blocked"]), e["blocked_until"] and self.sim_time(e["blocked_until"]), e["id"])
                           for e in self.edges])
            c.executemany(
                "INSERT OR REPLACE INTO tasks (id, bin_id, robot_id, created_at, assigned_at, completed_at, status, attempts)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(t["id"], t["bin_id"], t["robot_id"], self.sim_time(t["created"]),
                  t["assigned"] is not None and self.sim_time(t["assigned"]) or None,
                  t["completed"] is not None and self.sim_time(t["completed"]) or None,
                  t["status"], t["attempts"]) for t in self.tasks])
            c.execute("INSERT OR REPLACE INTO meta VALUES ('kpis', ?)", (json.dumps(self.kpis()),))
            c.commit()


def run_headless(num_robots, seed=42, minutes=DAY_END_MIN):
    """One full sim day with no database or dashboard. This is the `run_fn` for optimize.fleet_size_sweep."""
    w = World(num_robots=num_robots, seed=seed, live=False)
    for _ in range(minutes):
        w.tick()
    waits = w.final_waits() or [0]
    return {"avg_wait_min": round(sum(waits) / len(waits), 1), "max_wait_min": float(max(waits)),
            "overflow_minutes": float(w.overflow_minutes), "distance_m": round(w.dist_driven_m)}
