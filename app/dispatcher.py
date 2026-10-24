"""Task creation and robot assignment. Version 1 = greedy (the fallback)."""
from . import navigation as nav

PICKUP_THRESHOLD = 80.0  # bin becomes needs_pickup at this fill level
BATTERY_MARGIN_PCT = 5.0


def step(w):
    create_tasks(w)
    assign_greedy(w)


def create_tasks(w):
    open_bins = {t["bin_id"] for t in w.tasks if t["status"] in ("open", "assigned", "escalated")}
    for b in w.bins:
        if b["fill_pct"] >= PICKUP_THRESHOLD and b["id"] not in open_bins:
            w.new_task(b)
            w.log("task_created", f"Bin {b['id']} at {w.node_name(b['node_id'])} is {b['fill_pct']:.0f}% full: pickup requested",
                  bin_id=b["id"])


def assign_greedy(w):
    """For each open task (fullest bin first), give it to the robot with the lowest travel time
    that has the battery and capacity for the trip plus the return to a dock."""
    open_tasks = [t for t in w.tasks if t["status"] == "open"]
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
