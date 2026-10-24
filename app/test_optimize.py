
"""Run with:  python app/test_optimize.py   (keep this file local; it isn't part of the contract)"""
import random

from optimize import plan_routes, fleet_size_sweep, fleet_size_study

# ---- Contract example: 4 nodes, symmetric times of 3..10 minutes ----
NODES = ["dock", "a", "b", "c"]
T = [[0, 4, 6, 8],
     [4, 0, 3, 7],
     [6, 3, 0, 10],
     [8, 7, 10, 0]]
ROBOTS = [{"id": f"r{i}", "start": "dock", "end": "dock",
           "capacity_left": 60, "max_minutes": 40} for i in (1, 2)]
STOPS = [{"bin_id": "b1", "node": "a", "demand": 30},
         {"bin_id": "b2", "node": "b", "demand": 30},
         {"bin_id": "b3", "node": "c", "demand": 30}]


def route_minutes(route, stops_by_id, robot):
    path = [robot["start"]] + [stops_by_id[b]["node"] for b in route] + [robot["end"]]
    ix = {n: i for i, n in enumerate(NODES)}
    return sum(T[ix[p]][ix[q]] for p, q in zip(path, path[1:]))


def test_contract_example():
    out = plan_routes(NODES, T, ROBOTS, STOPS, time_limit_s=0.5)
    by_id = {s["bin_id"]: s for s in STOPS}
    assert out["unassigned"] == [], out
    assigned = [b for r in out["routes"].values() for b in r]
    assert sorted(assigned) == ["b1", "b2", "b3"], "each stop exactly once"
    for robot in ROBOTS:
        route = out["routes"][robot["id"]]
        assert sum(by_id[b]["demand"] for b in route) <= robot["capacity_left"]
        assert route_minutes(route, by_id, robot) <= robot["max_minutes"]
    print("contract example OK:", out)


def test_too_big_goes_unassigned():
    stops = STOPS + [{"bin_id": "huge", "node": "a", "demand": 100}]
    out = plan_routes(NODES, T, ROBOTS, stops, time_limit_s=0.5)
    assert "huge" in out["unassigned"]
    print("oversized bin unassigned OK")


def test_battery_limit_drops_far_stop():
    robots = [{"id": "r1", "start": "dock", "end": "dock",
               "capacity_left": 100, "max_minutes": 9}]
    out = plan_routes(NODES, T, robots, STOPS, time_limit_s=0.5)
    assert "b3" in out["unassigned"]       # dock->c->dock = 16 min > 9
    print("battery limit OK:", out)


def test_empty_inputs():
    assert plan_routes(NODES, T, ROBOTS, [])["routes"] == {"r1": [], "r2": []}
    assert plan_routes(NODES, T, [], STOPS)["unassigned"] == ["b1", "b2", "b3"]
    print("empty inputs OK")


def test_same_node_two_bins():
    stops = [{"bin_id": "x", "node": "a", "demand": 20},
             {"bin_id": "y", "node": "a", "demand": 20}]
    out = plan_routes(NODES, T, ROBOTS, stops, time_limit_s=0.5)
    assert out["unassigned"] == []
    print("two bins at one node OK")


def test_balance_weight_still_valid():
    out = plan_routes(NODES, T, ROBOTS, STOPS, time_limit_s=0.5, balance_weight=10)
    assert out["unassigned"] == [], out
    assert sorted(b for r in out["routes"].values() for b in r) == ["b1", "b2", "b3"]
    print("balance_weight OK:", out)


# ---- Sweep tests with a fake run function ----
def fake_run(n, seed):
    rng = random.Random(seed * 100 + n)          # same seeds for every fleet size
    base = 60.0 / n
    return {"avg_wait_min": base * 0.5 + rng.uniform(-1, 1),
            "max_wait_min": base + rng.uniform(-2, 2),
            "overflow_minutes": max(0.0, 40 - 8 * n + rng.uniform(-3, 3))}


def test_sweep():
    out = fleet_size_sweep(fake_run)
    assert [r["robots"] for r in out["results"]] == list(range(2, 9))
    assert out["recommended"] == 4, out["recommended"]   # 60/4 = 15 +- noise
    assert fleet_size_sweep(fake_run, target_max_wait_min=0.1)["recommended"] is None
    print("sweep OK: recommended =", out["recommended"])


def test_study():
    out = fleet_size_study(fake_run, seeds=range(20))
    row = out["results"][0]
    assert row["n_seeds"] == 20 and 0 <= row["share_meeting_target"] <= 1
    print("study OK: recommended =", out["recommended"])
    for r in out["results"]:
        print(f'  {r["robots"]} robots: p95 max wait {r["max_wait_p95"]:.1f} min, '
              f'{r["share_meeting_target"]:.0%} of days meet target')


if __name__ == "__main__":
    test_sweep()
    test_study()
    test_empty_inputs()
    test_contract_example()
    test_too_big_goes_unassigned()
    test_battery_limit_drops_far_stop()
    test_same_node_two_bins()
    test_balance_weight_still_valid()
    print("\nAll tests passed.")
