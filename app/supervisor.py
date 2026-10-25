"""Autonomy supervisor: watches every robot and the fleet, fixes what it can, escalates the rest.

Robot states (IDLE, EN_ROUTE, COLLECTING, RETURNING, UNLOADING, CHARGING) are driven by sim.py;
this module adds STUCK and ESCALATED and runs the detectors. Every action writes an event.
"""
from . import navigation as nav, notify

STUCK_MIN = 5            # sim-minutes without progress before a robot counts as stuck (and again before escalating)
LOOP_WINDOW = 8          # last N node arrivals examined for looping
LOOP_MAX_DISTINCT = 3    # ...if they cover this few nodes or fewer, the robot is going in circles
BATTERY_RESERVE_PCT = 5.0
MAX_TASK_ATTEMPTS = 3
ENERGY_BUDGET_PCT_PER_ROBOT = 400.0   # total battery % the fleet may burn per robot before dispatch pauses
OVERFLOW_ALERT_COOLDOWN_MIN = 15   # at most one overflow-risk alert per site per window; bins at risk are summarized
WATCHED = ("EN_ROUTE", "COLLECTING", "RETURNING", "UNLOADING")


def step(w):
    for r in w.robots:
        if r["state"] == "ESCALATED":
            continue
        _check_battery(w, r)
        if r["online"]:  # the server cannot observe an offline robot's progress; the lease check covers it
            _check_looping(w, r)
            _check_stuck(w, r)
    _check_leases(w)
    _check_budget(w)
    _check_overflow_risk(w)


# ---- stuck -----------------------------------------------------------------------------------
def _check_stuck(w, r):
    stale = w.t - r["last_progress"]
    if r["state"] in WATCHED and stale >= STUCK_MIN:
        r["prev_state"], r["state"], r["stuck_since"] = r["state"], "STUCK", w.t
        w.log("stuck", f"Robot {r['id']} stuck: no progress for {stale} min, retrying route", robot_id=r["id"])
        _retry(w, r)
    elif r["state"] == "STUCK":
        if _retry(w, r):
            return
        if w.t - r["stuck_since"] >= STUCK_MIN:
            _escalate(w, r, f"stuck for {w.t - r['last_progress']} min")


def _retry(w, r):
    """Try to get a stuck robot moving again. Frozen (hardware-dead) robots can't be helped this way."""
    if r["frozen"] or r["battery"] <= 0:
        return False
    if r["target"] is not None and r["prev_state"] in ("EN_ROUTE", "RETURNING") and not w._replan(r):
        return False
    r["state"], r["stuck_since"], r["last_progress"] = r["prev_state"], None, w.t
    w.log("recovered", f"Robot {r['id']} recovered and is moving again", robot_id=r["id"])
    return True


def _escalate(w, r, reason):
    """Take the robot out of service, hand its task back for reassignment, and tell a human."""
    bins = list(r["route"])
    w.release_task(r, reason, quiet=True)
    r["state"], r["path"], r["seg"], r["stuck_since"] = "ESCALATED", [], None, None
    where = w.node_name(r["node"])
    msg = f"Robot {r['id']} {reason} near {where}"
    if bins:
        msg += f"; task for bin {', '.join(bins)} reassigned"
    notify.alert(w, msg + ". Needs a human.", robot_id=r["id"], bin_id=bins[0] if bins else None)


# ---- connection loss -------------------------------------------------------------------------
def _check_leases(w):
    """Reassign an offline robot's bins only after its lease (plus a short grace) has run out. By then the
    robot's own offline instructions have made it stand down, so two robots never go for the same bin."""
    for r in w.robots:
        if r["online"] or r["lease_handled"] or w.t < r["lease_until"] + w.SERVER_GRACE_MIN:
            continue
        r["lease_handled"] = True
        mine = [t for t in w.tasks if t["robot_id"] == r["id"] and t["status"] == "assigned"]
        for t in mine:
            t["status"], t["robot_id"] = "open", None
            w._refresh_bin_status(w.bin_by_id[t["bin_id"]])
        text = f"Robot {r['id']} has been out of contact for {w.t - r['offline_since']} min"
        text += f"; its {len(mine)} unfinished bins were reassigned." if mine else "."
        notify.alert(w, text + " Needs a human.", robot_id=r["id"])


# ---- looping ---------------------------------------------------------------------------------
def _check_looping(w, r):
    if r["state"] not in ("EN_ROUTE", "RETURNING"):
        return
    v = r["visits"][-LOOP_WINDOW:]
    if len(v) >= LOOP_WINDOW and len(set(v)) <= LOOP_MAX_DISTINCT:
        w.log("looping", f"Robot {r['id']} is looping between {', '.join(sorted({w.node_name(n) for n in v}))}",
              robot_id=r["id"])
        _escalate(w, r, "looping without reaching its target")


# ---- low battery -----------------------------------------------------------------------------
def _check_battery(w, r):
    """Abort a task if the battery can't cover the rest of the trip plus the return to a dock."""
    if r["state"] != "EN_ROUTE" or not r["route"]:
        return
    stop = w.bin_by_id[r["route"][-1]]
    dock = w.nearest_dock(stop["node_id"])
    if dock is None:
        return
    need = (w.remaining_path_m(r) + dock[1]) * w.DRAIN_PER_M * r["drain_mult"]
    if r["battery"] - need >= BATTERY_RESERVE_PCT:
        return
    bins = list(r["route"])
    w.release_task(r, "low battery", quiet=True)
    w.log("low_battery", f"Robot {r['id']} aborted pickup of bin {', '.join(bins)}: battery {r['battery']:.0f}% "
                         f"can't cover the trip; returning to dock, task reassigned", robot_id=r["id"], bin_id=bins[0])
    home = w.nearest_dock(r["node"]) if not r["seg"] else w.nearest_dock(r["seg"][1])
    if home and w.begin_path_from(r, home[0]):
        r["state"], r["last_progress"] = "RETURNING", w.t
    else:
        r["state"] = "IDLE"


# ---- fleet-level -----------------------------------------------------------------------------
def _check_budget(w):
    if w.dispatch_paused:
        return
    over = [t for t in w.tasks if t["attempts"] >= MAX_TASK_ATTEMPTS and t["status"] != "done"]
    if over:
        w.dispatch_paused = True
        notify.alert(w, f"Bin {over[0]['bin_id']} has failed {over[0]['attempts']} pickup attempts. "
                        f"New dispatches paused.", bin_id=over[0]["bin_id"])
    elif w.energy_pct > ENERGY_BUDGET_PCT_PER_ROBOT * len(w.robots):
        w.dispatch_paused = True
        notify.alert(w, f"Fleet energy use ({w.energy_pct:.0f}%) is over budget. New dispatches paused.")


def _check_overflow_risk(w):
    """Alert when bins will overflow before any robot could get there. Alerts are batched: one
    summary per cooldown window, so a big site doesn't flood a human's phone."""
    alerted = w.__dict__.setdefault("overflow_alerted", set())
    for b in w.bins:
        if b["id"] in alerted and b["fill_pct"] < 50:
            alerted.discard(b["id"])  # emptied: re-arm
    last = w.__dict__.get("overflow_alert_t", -10**9)
    if w.t - last < OVERFLOW_ALERT_COOLDOWN_MIN:
        return
    assigned = {t["bin_id"] for t in w.tasks if t["status"] == "assigned"}
    mult = w.current_fill_multiplier()
    at_risk = []  # (minutes_left, bin, eta)
    for b in w.bins:
        if b["id"] in alerted or b["fill_pct"] < 80 or b["id"] in assigned:
            continue
        minutes_left = max(0.0, (100.0 - b["fill_pct"]) / max(b["rate"] * mult / 60.0, 0.01))
        eta = _best_eta_min(w, b)
        if eta is None or eta > minutes_left:
            at_risk.append((minutes_left, b, eta))
    if not at_risk:
        return
    at_risk.sort(key=lambda x: x[0])
    minutes_left, worst, eta = at_risk[0]
    alerted.update(b["id"] for _, b, _ in at_risk)
    w.overflow_alert_t = w.t
    when = "is overflowing" if worst["fill_pct"] >= 100 else f"will overflow in ~{minutes_left:.0f} min"
    who = "no robot can reach it" if eta is None else f"the nearest robot is ~{eta:.0f} min away"
    msg = f"Bin {worst['id']} at {w.node_name(worst['node_id'])} {when} and {who}."
    if len(at_risk) > 1:
        msg = f"{len(at_risk)} bins at risk of overflowing. Worst: " + msg[0].lower() + msg[1:]
    notify.alert(w, msg, bin_id=worst["id"])


def _best_eta_min(w, b):
    best = None
    for r in w.robots:
        if r["frozen"] or r["state"] in ("ESCALATED", "STUCK") or r["battery"] <= 0 or not r["online"]:
            continue
        p = nav.shortest_path(w.graph, r["node"], b["node_id"])
        if p is None:
            continue
        eta = p[1] / w.SPEED_M_PER_MIN + (0 if r["state"] == "IDLE" else 10)
        best = eta if best is None else min(best, eta)
    return best
