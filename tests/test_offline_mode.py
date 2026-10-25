"""Offline-mode checks: a robot that loses its connection must never collide with the server's plan.

Run from the repo root:  python tests/test_offline_mode.py   (or pytest)
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import sim, sites  # noqa: E402


def world(site_id="airport", robots=4):
    return sim.World(site=sites.get(site_id), num_robots=robots, seed=3)


def busy_robot(w):
    """Tick until some robot is heading to a bin, and return it."""
    for _ in range(400):
        w.tick()
        r = next((r for r in w.robots if r["route"] and r["state"] == "EN_ROUTE"), None)
        if r:
            return r
    raise AssertionError("no robot ever got a route")


def far_robot(w, min_minutes=5):
    """Tick until some robot is heading to a bin that is still at least `min_minutes` of walking away."""
    for _ in range(700):
        w.tick()
        r = next((r for r in w.robots if r["route"] and r["state"] == "EN_ROUTE"
                  and w.remaining_path_m(r) >= min_minutes * w.SPEED_M_PER_MIN), None)
        if r:
            return r
    raise AssertionError("never saw a robot with a long way to go")


def holders(w):
    """bin id -> robots the server currently has it assigned to."""
    out = {}
    for t in w.tasks:
        if t["status"] == "assigned":
            out.setdefault(t["bin_id"], []).append(t["robot_id"])
    return out


def test_short_outage_keeps_working_and_syncs():
    w = world()
    r = busy_robot(w)
    mine = list(r["route"])
    w.drop_signal(r["id"], minutes=10)               # shorter than the 25 min lease
    for _ in range(12):
        w.tick()
    assert r["online"], "should have reconnected by itself"
    assert w.conflicts == 0
    kinds = [e["kind"] for e in w.events if e["robot_id"] == r["id"]]
    assert "signal_lost" in kinds and "signal_restored" in kinds
    # nothing it was holding was handed to anyone else in the meantime
    assert not any(e["kind"] == "alert" and r["id"] in e["message"] for e in w.events)
    restored = next(e for e in w.events if e["kind"] == "signal_restored")
    assert "synced" in restored["message"], mine


def test_offline_events_reach_the_server_only_on_reconnect():
    w = world()
    r = busy_robot(w)
    w.drop_signal(r["id"], minutes=20)
    seen_before = len(w.events)
    for _ in range(19):
        w.tick()
    during = [e for e in w.events[seen_before:] if e["robot_id"] == r["id"] and e["kind"] in w.ROBOT_SIDE_KINDS]
    assert not during, "robot-side events must be held back while offline"
    w.tick(); w.tick()
    assert r["online"]
    assert any("synced after reconnect" in e["message"] for e in w.events) or not r["offline_log"]


def test_long_outage_lease_expiry_then_reassign_without_conflict():
    w = world()
    r = busy_robot(w)
    held = list(r["route"])
    w.drop_signal(r["id"], minutes=60)               # outlasts the lease
    for _ in range(w.LEASE_MIN + w.SERVER_GRACE_MIN + 2):
        w.tick()
        # at no moment may the server hand an offline robot's bin to someone else while the robot may still use it
        for bid, who in holders(w).items():
            assert len(who) == 1, (bid, who)
    assert any(e["kind"] == "alert" and "out of contact" in e["message"] for e in w.events), "human should be told"
    assert not r["route"], "robot must have dropped its stops by itself"
    for _ in range(80):
        w.tick()
    assert w.conflicts == 0
    assert all(t["status"] != "assigned" or t["robot_id"] != r["id"] for t in w.tasks), "server released its bins"


def test_reconnect_after_reassignment_stands_down():
    w = world()
    r = busy_robot(w)
    w.drop_signal(r["id"], minutes=50)
    for _ in range(w.LEASE_MIN + w.SERVER_GRACE_MIN + 5):
        w.tick()
    w.restore_signal(r["id"])
    for _ in range(60):
        w.tick()
    assert r["online"] and w.conflicts == 0


def test_random_outages_never_double_book_a_bin():
    for site_id, robots, seed in (("airport", 6, 1), ("airport", 4, 2), ("ucsd", 12, 3)):
        w = sim.World(site=sites.get(site_id), num_robots=robots, seed=seed)
        rng = random.Random(seed)
        for _ in range(sim.DAY_END_MIN):
            if rng.random() < 0.04:
                w.drop_signal(rng.choice(w.robots)["id"], minutes=rng.randint(3, 50))
            w.tick()
            for bid, who in holders(w).items():
                assert len(who) == 1, (site_id, w.t, bid, who)
        assert w.conflicts == 0, (site_id, w.conflicts)
        assert w.pickups > 0


def test_lease_expiring_mid_route_makes_the_robot_stand_down_before_the_server_reassigns():
    w = world("ucsd", robots=10)
    w.LEASE_MIN = 2                                    # shorter than the trip, so the lease expires mid-route
    r = far_robot(w)
    held = list(r["route"])
    w.drop_signal(r["id"], minutes=90)
    lease_end = r["lease_until"]
    aborted_at = reassigned_at = None
    for _ in range(40):
        w.tick()
        if aborted_at is None and not r["route"]:
            aborted_at = w.t
        if reassigned_at is None and any(t["status"] == "open" for t in w.tasks if t["bin_id"] in held):
            reassigned_at = w.t                        # the server took the bin back
        for bid, who in holders(w).items():
            assert len(who) == 1, (bid, who)
    assert aborted_at is not None, "robot should have dropped its stops itself"
    assert reassigned_at is not None and reassigned_at >= aborted_at, (aborted_at, reassigned_at)
    assert reassigned_at >= lease_end + w.SERVER_GRACE_MIN, "server must wait out lease + grace"
    assert any(k == "offline_abort" for _, k, _, _ in r["offline_log"]), "abort is held on the robot until reconnect"
    assert w.conflicts == 0


def test_random_outages_with_short_leases_still_never_conflict():
    aborts = 0
    configs = [(site_id, robots, seed) for site_id, robots in (("airport", 6), ("airport", 4), ("ucsd", 12))
               for seed in (1, 2, 3)]
    for site_id, robots, seed in configs:
        w = sim.World(site=sites.get(site_id), num_robots=robots, seed=seed)
        w.LEASE_MIN = 4                                # leases expire mid-route often, exercising the stand-down path
        rng = random.Random(seed)
        for _ in range(sim.DAY_END_MIN):
            if rng.random() < 0.05:
                w.drop_signal(rng.choice(w.robots)["id"], minutes=rng.randint(8, 50))
            w.tick()
            for bid, who in holders(w).items():
                assert len(who) == 1, (site_id, w.t, bid, who)
        aborts += w.offline_aborts
        assert w.conflicts == 0, (site_id, w.conflicts)
    assert aborts > 0, "the stress test never exercised the lease stand-down"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"{len(tests)} passed")
