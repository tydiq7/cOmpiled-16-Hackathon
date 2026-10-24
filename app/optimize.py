"""app/optimize.py  (owner: Teammate 2)

Route optimization (capacitated vehicle routing via OR-Tools) and fleet sizing.
Matches Contract 2 exactly. Depends on nothing else in the repo.

    pip install ortools
"""
import math
import statistics

SCALE = 100               # OR-Tools needs integers: minutes and % are stored x100
UNREACHABLE_MIN = 1000.0  # stand-in cost for None/inf entries (blocked paths)


def _cost(minutes):
    """Minutes -> integer solver cost. None/inf (no path) become a huge cost."""
    if minutes is None or not math.isfinite(minutes):
        minutes = UNREACHABLE_MIN
    return int(round(min(minutes, UNREACHABLE_MIN) * SCALE))


# ----------------------------------------------------------------------------
# Contract 2, function 1
# ----------------------------------------------------------------------------
def plan_routes(nodes, travel_min, robots, stops, time_limit_s=2.0, balance_weight=0):
    """Assign bins to robots and order each robot's stops to minimize total travel time.

    See Contract 2 for argument shapes. Returns
        {"routes": {robot_id: [bin_id, ...]}, "unassigned": [bin_id, ...]}
    Bins that cannot fit (capacity or battery) go in "unassigned"; nothing raises
    for infeasibility. If the solver finds no plan at all, every bin is returned
    as unassigned so the dispatcher can fall back to greedy assignment.

    balance_weight (optional, default 0 = exactly the contract behavior): if > 0,
    also penalizes the longest route, which spreads bins across robots instead of
    chaining them onto one. Larger values favor balance over total travel.
    """
    robot_ids = [r["id"] for r in robots]
    routes = {rid: [] for rid in robot_ids}
    stop_ids = [s["bin_id"] for s in stops]
    if not stops or not robots:
        return {"routes": routes, "unassigned": list(stop_ids)}

    from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # lazy import

    node_idx = {name: i for i, name in enumerate(nodes)}

    def lookup(name):
        if name not in node_idx:
            raise KeyError(f"node '{name}' is not in the nodes list")
        return node_idx[name]

    # Solver locations: one per stop (so two bins at the same node stay separate),
    # then one per distinct robot start/end node.
    n_stops = len(stops)
    loc_node = [lookup(s["node"]) for s in stops]
    depot_loc = {}
    starts, ends = [], []
    for r in robots:
        for key, out in (("start", starts), ("end", ends)):
            ni = lookup(r[key])
            if ni not in depot_loc:
                depot_loc[ni] = len(loc_node)
                loc_node.append(ni)
            out.append(depot_loc[ni])
    n_loc = len(loc_node)

    cost = [[0 if i == j else _cost(travel_min[loc_node[i]][loc_node[j]])
             for j in range(n_loc)] for i in range(n_loc)]

    manager = pywrapcp.RoutingIndexManager(n_loc, len(robots), starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    # Travel time: both the objective and a per-robot battery limit.
    def transit(from_index, to_index):
        return cost[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_cb = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)
    routing.AddDimensionWithVehicleCapacity(
        transit_cb, 0,
        [int(round(r["max_minutes"] * SCALE)) for r in robots],
        True, "Time")

    # Load: each stop adds its demand; robots can't exceed capacity_left.
    demands = [int(round(s["demand"] * SCALE)) for s in stops] + [0] * (n_loc - n_stops)

    def demand(from_index):
        return demands[manager.IndexToNode(from_index)]

    demand_cb = routing.RegisterUnaryTransitCallback(demand)
    routing.AddDimensionWithVehicleCapacity(
        demand_cb, 0,
        [int(round(r["capacity_left"] * SCALE)) for r in robots],
        True, "Load")

    if balance_weight:
        routing.GetDimensionOrDie("Time").SetGlobalSpanCostCoefficient(int(balance_weight))

    # Every stop is optional, with a penalty bigger than any detour, so the solver
    # serves as many bins as it can and drops the rest instead of failing.
    max_arc = max(max(row) for row in cost)
    penalty = (max_arc + 1) * (n_loc + 1)
    for i in range(n_stops):
        routing.AddDisjunction([manager.NodeToIndex(i)], penalty)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION)
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    params.time_limit.FromMilliseconds(max(1, int(time_limit_s * 1000)))

    solution = routing.SolveWithParameters(params)
    if solution is None:
        return {"routes": routes, "unassigned": list(stop_ids)}

    served = set()
    for v, rid in enumerate(robot_ids):
        index = routing.Start(v)
        while not routing.IsEnd(index):
            loc = manager.IndexToNode(index)
            if loc < n_stops:
                routes[rid].append(stops[loc]["bin_id"])
                served.add(stops[loc]["bin_id"])
            index = solution.Value(routing.NextVar(index))

    unassigned = [b for b in stop_ids if b not in served]
    return {"routes": routes, "unassigned": unassigned}


# ----------------------------------------------------------------------------
# Contract 2, function 2
# ----------------------------------------------------------------------------
def fleet_size_sweep(run_fn, sizes=range(2, 9), target_max_wait_min=15.0, seed=42):
    """Find the smallest fleet that meets the service target (single seed).

    run_fn(num_robots, seed) -> {"avg_wait_min", "max_wait_min", "overflow_minutes"}
    Returns {"results": [...one row per size...], "recommended": int | None}.
    The same seed is used for every size so the comparison is paired.
    """
    results = []
    for n in sizes:
        out = run_fn(n, seed)
        results.append({
            "robots": n,
            "avg_wait_min": out["avg_wait_min"],
            "max_wait_min": out["max_wait_min"],
            "overflow_minutes": out["overflow_minutes"],
        })
    recommended = next(
        (r["robots"] for r in results if r["max_wait_min"] <= target_max_wait_min), None)
    return {"results": results, "recommended": recommended}


# ----------------------------------------------------------------------------
# Extra (not in the contract): the data-science version of the sweep
# ----------------------------------------------------------------------------
def _percentile(values, p):
    """Linear-interpolated percentile (p in 0..100) without needing numpy."""
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def fleet_size_study(run_fn, sizes=range(2, 9), seeds=range(20),
                     target_max_wait_min=15.0, required_share=0.95):
    """Multi-seed fleet sizing: same seeds for every size, with uncertainty.

    Each row reports, over all seeds: mean and 95% CI half-width of avg wait,
    mean and p95 of max wait, mean overflow minutes, and the share of simulated
    days that met the target. `recommended` is the smallest fleet whose share
    meets `required_share` (default: 95% of days), or None.
    """
    seeds = list(seeds)
    rows = []
    for n in sizes:
        runs = [run_fn(n, s) for s in seeds]
        avg_w = [r["avg_wait_min"] for r in runs]
        max_w = [r["max_wait_min"] for r in runs]
        over = [r["overflow_minutes"] for r in runs]
        sd = statistics.stdev(avg_w) if len(avg_w) > 1 else 0.0
        rows.append({
            "robots": n,
            "n_seeds": len(seeds),
            "avg_wait_min": statistics.mean(avg_w),
            "avg_wait_ci95": 1.96 * sd / math.sqrt(len(avg_w)),
            "max_wait_mean": statistics.mean(max_w),
            "max_wait_p95": _percentile(max_w, 95),
            "overflow_minutes": statistics.mean(over),
            "share_meeting_target": sum(m <= target_max_wait_min for m in max_w) / len(max_w),
        })
    recommended = next(
        (r["robots"] for r in rows if r["share_meeting_target"] >= required_share), None)
    return {"results": rows, "recommended": recommended}
