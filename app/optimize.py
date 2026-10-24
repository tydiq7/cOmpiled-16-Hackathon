"""Optimizer. OWNED BY TEAMMATE 2 -- placeholder stubs matching Contract 2."""


def plan_routes(nodes, travel_min, robots, stops, time_limit_s=2.0):
    # Stub: assign nothing; the dispatcher falls back to greedy.
    return {"routes": {r["id"]: [] for r in robots}, "unassigned": [s["bin_id"] for s in stops]}


def fleet_size_sweep(run_fn, sizes=range(2, 9), target_max_wait_min=15.0, seed=42):
    results = []
    for n in sizes:
        results.append({"robots": n, **run_fn(n, seed)})
    ok = [r["robots"] for r in results if r["max_wait_min"] <= target_max_wait_min]
    return {"results": results, "recommended": min(ok) if ok else None}
