"""Task creation and robot assignment. Version 1 = greedy (the fallback)."""
import inspect

from . import navigation as nav, optimize

PICKUP_THRESHOLD = 80.0  # bin becomes needs_pickup at this fill level
BATTERY_MARGIN_PCT = 5.0
PLAN_EVERY_MIN = 5         # batch window for optimizer plans
MIN_PLAN_GAP_MIN = 2       # never re-plan more often than this, even when bins are urgent (solver cost)
URGENT_FILL_PCT = 95.0     # plan immediately if a waiting bin is this full
EXTRA_BIN_PCT = 60.0       # bins this full and near a pickup ride along on the same trip
EXTRA_BIN_RADIUS_M = 300.0
BALANCE_WEIGHT = 1000      # spread bins across robots instead of chaining them on one (tuned in headless sweeps)
MAX_PLAN_STOPS = 80        # most urgent stops handed to the solver, so huge sites stay fast
GREEDY_AFTER_MIN = 2 * PLAN_EVERY_MIN  # a task the planner can't place this long gets the greedy treatment


def step(w):
    create_tasks(w)
    if w.dispatch_paused:
        return
    if w.use_optimizer:
        planned = plan_with_optimizer(w)
        if not planned:  # solver failed, timed out, or returned nothing usable: version 1 takes over
            assign_greedy(w)
        else:  # leftovers the planner couldn't place still shouldn't wait forever
            assign_greedy(w, min_age=GREEDY_AFTER_MIN)
    else:
        assign_greedy(w)


def plan_with_optimizer(w):
    """Version 2: hand every idle robot a multi-stop route. Returns False if the optimizer was
    not used or gave nothing (caller falls back to greedy), True if planning ran."""
    open_tasks = [t for t in w.tasks if t["status"] == "open"]
    idle = [r for r in w.robots if r["state"] == "IDLE" and not r["frozen"] and not r["route"]
            and r["battery"] > w.LOW_BATTERY_PCT]
    if not open_tasks or not idle:
        return True  # nothing to do is not a failure
    if w.t - w.__dict__.get("last_plan_t", -10**9) < MIN_PLAN_GAP_MIN:
        return True
    urgent = any(w.bin_by_id[t["bin_id"]]["fill_pct"] >= URGENT_FILL_PCT for t in open_tasks)
    if not urgent and w.t % PLAN_EVERY_MIN != 0:
        return True  # wait for the batch window
    w.last_plan_t = w.t
    stops = _candidate_stops(w, open_tasks)[:MAX_PLAN_STOPS]
    robots = []
    for r in idle:
        dock = w.nearest_dock(r["node"])
        if dock is None:
            continue
        spare_pct = max(0.0, r["battery"] - w.LOW_BATTERY_PCT)
        robots.append({"id": r["id"], "start": r["node"], "end": dock[0], "capacity_left": 100.0 - r["load"],
                       "max_minutes": spare_pct / w.DRAIN_PER_M / w.SPEED_M_PER_MIN})
    if not robots:
        return False
    nodes = sorted({x["start"] for x in robots} | {x["end"] for x in robots} | {s["node"] for s in stops})
    travel = nav.travel_matrix(w.graph, nodes, w.SPEED_M_PER_MIN)
    try:
        extra = {"balance_weight": BALANCE_WEIGHT} if "balance_weight" in inspect.signature(optimize.plan_routes).parameters else {}
        result = optimize.plan_routes(nodes, travel, robots, stops, time_limit_s=w.plan_time_limit_s, **extra)
        routes = {rid: list(bins) for rid, bins in result["routes"].items() if bins}
    except Exception as exc:  # a broken solver must never stop the fleet
        w.log("planner_error", f"Route planner failed ({type(exc).__name__}); using greedy dispatch")
        return False
    if not routes:
        return False
    for rid, bin_ids in routes.items():
        _assign_route(w, w.robot_by_id[rid], bin_ids)
    return True


def _candidate_stops(w, open_tasks):
    """Open pickups plus nearly-full bins close to one of them."""
    stops, seen = [], set()
    open_tasks = sorted(open_tasks, key=lambda t: -w.bin_by_id[t["bin_id"]]["fill_pct"])  # fullest first
    for t in open_tasks:
        b = w.bin_by_id[t["bin_id"]]
        stops.append({"bin_id": b["id"], "node": b["node_id"], "demand": w.bin_demand_pct(b)})
        seen.add(b["id"])
    anchors = {w.bin_by_id[t["bin_id"]]["node_id"] for t in open_tasks}
    for b in w.bins:
        if b["id"] in seen or b["fill_pct"] < EXTRA_BIN_PCT or w.has_open_task(b["id"]):
            continue
        if any((nav.distance(w.graph, a, b["node_id"]) or 1e9) <= EXTRA_BIN_RADIUS_M for a in anchors):
            stops.append({"bin_id": b["id"], "node": b["node_id"], "demand": w.bin_demand_pct(b)})
    return stops


def _assign_route(w, robot, bin_ids):
    parts = []
    for bid in bin_ids:
        b = w.bin_by_id[bid]
        task = next((t for t in w.tasks if t["bin_id"] == bid and t["status"] == "open"), None)
        if task is None:  # a ride-along bin that wasn't over the pickup threshold yet
            task = w.new_task(b)
        parts.append(f"{bid} ({b['fill_pct']:.0f}%)")
        w.assign(task, robot, bin_ids)
    w.log("dispatch", f"Robot {robot['id']} planned route: {' -> '.join(parts)}"
                      f" ({len(bin_ids)} stop{'s' if len(bin_ids) != 1 else ''}, one trip)",
          robot_id=robot["id"], bin_id=bin_ids[0])


def create_tasks(w):
    open_bins = {t["bin_id"] for t in w.tasks if t["status"] in ("open", "assigned", "escalated")}
    for b in w.bins:
        if b["fill_pct"] >= PICKUP_THRESHOLD and b["id"] not in open_bins:
            w.new_task(b)
            w.log("task_created", f"Bin {b['id']} at {w.node_name(b['node_id'])} is {b['fill_pct']:.0f}% full: pickup requested",
                  bin_id=b["id"])


def assign_greedy(w, min_age=0):
    """For each open task (fullest bin first), give it to the robot with the lowest travel time
    that has the battery and capacity for the trip plus the return to a dock."""
    open_tasks = [t for t in w.tasks if t["status"] == "open" and w.t - t["created"] >= min_age]
    open_tasks.sort(key=lambda t: -w.bin_by_id[t["bin_id"]]["fill_pct"])
    for task in open_tasks:
        b = w.bin_by_id[task["bin_id"]]
        demand = w.bin_demand_pct(b)
        best = None
        for r in w.robots:
            if r["state"] != "IDLE" or r["frozen"] or r["route"]:
                continue
            to_bin = nav.shortest_path(w.graph, r["node"], b["node_id"])
            if to_bin is None:
                continue
            back = w.nearest_dock(b["node_id"])
            if back is None:
                continue
            trip_m = to_bin[1] + back[1]
            if r["battery"] - trip_m * w.DRAIN_PER_M < w.LOW_BATTERY_PCT + BATTERY_MARGIN_PCT:
                continue
            if r["load"] + demand > 100:
                continue
            if best is None or to_bin[1] < best[1]:
                best = (r, to_bin[1])
        if best:
            r, dist = best
            w.assign(task, r, [b["id"]])
            w.log("dispatch",
                  f"Robot {r['id']} dispatched to bin {b['id']} at {w.node_name(b['node_id'])} "
                  f"({b['fill_pct']:.0f}% full, ~{dist / w.SPEED_M_PER_MIN:.0f} min away)",
                  robot_id=r["id"], bin_id=b["id"])
