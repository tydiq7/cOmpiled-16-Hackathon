"""Fleet-sizing sweep, runnable in a separate process so its solver work can't slow the live API."""
import os

from . import optimize, sites
from .sim import run_headless

SWEEP_SEEDS = int(os.environ.get("SWEEP_SEEDS", "5"))   # simulated days per fleet size
SWEEP_REQUIRED_SHARE = 0.8                               # recommend the smallest fleet that meets the target on this share of days


def sweep_site(site_id):
    """Multi-seed fleet-sizing study, shaped into Contract 1 `fleet_sizing` rows (extra fields ride along)."""
    site = sites.get(site_id)
    def run(n, seed):
        # Service target: 95% of bins emptied within the target wait. The single worst bin on a big site is
        # mostly luck, so the Contract 1 `max_wait_min` field carries each day's 95th-percentile wait.
        r = run_headless(n, seed, site=site)
        return {"avg_wait_min": r["avg_wait_min"], "max_wait_min": r["p95_wait_min"],
                "overflow_minutes": r["overflow_minutes"]}

    def study_of(sizes):
        return optimize.fleet_size_study(run, sizes=sizes, seeds=range(SWEEP_SEEDS),
                                         required_share=SWEEP_REQUIRED_SHARE)

    study = study_of(site.sweep_sizes)
    if study["recommended"] is None and site.sweep_max and site.sweep_max > max(site.sweep_sizes):
        # nothing in the first range meets the target: extend the search upward
        more = study_of(range(max(site.sweep_sizes) + 1, site.sweep_max + 1))
        study = {"results": study["results"] + more["results"], "recommended": more["recommended"]}
    elif study["recommended"] is not None and study["recommended"] == min(site.sweep_sizes) > 2:
        # even the smallest size tried passes, so walk down until a fleet fails: the answer must be the true minimum
        n = study["recommended"] - 1
        while n >= 2:
            one = study_of([n])
            study["results"] = one["results"] + study["results"]
            if one["recommended"] is None:
                break
            study["recommended"] = n
            n -= 1
    # `max_wait_min` carries a typical day's 95th-percentile wait (the service level the target is judged on)
    rows = [{"robots": r["robots"], "avg_wait_min": round(r["avg_wait_min"], 1),
             "max_wait_min": round(r["max_wait_mean"], 1), "overflow_minutes": round(r["overflow_minutes"], 1),
             "avg_wait_ci95": round(r["avg_wait_ci95"], 1), "share_meeting_target": round(r["share_meeting_target"], 2),
             "n_seeds": r["n_seeds"]} for r in study["results"]]
    return {"results": rows, "recommended": study["recommended"]}
