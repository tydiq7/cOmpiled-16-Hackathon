"""Fleet-sizing sweep, runnable in a separate process so its solver work can't slow the live API."""
import os

from . import optimize, sites
from .sim import run_headless

SWEEP_SEEDS = int(os.environ.get("SWEEP_SEEDS", "5"))   # simulated days per fleet size
SWEEP_REQUIRED_SHARE = 0.8                               # recommend the smallest fleet that meets the target on this share of days


def sweep_site(site_id):
    """Multi-seed fleet-sizing study, shaped into Contract 1 `fleet_sizing` rows (extra fields ride along)."""
    site = sites.get(site_id)
    run = lambda n, seed: run_headless(n, seed, site=site)
    study = optimize.fleet_size_study(run, seeds=range(SWEEP_SEEDS), required_share=SWEEP_REQUIRED_SHARE)
    rows = [{"robots": r["robots"], "avg_wait_min": round(r["avg_wait_min"], 1),
             "max_wait_min": round(r["max_wait_p95"], 1), "overflow_minutes": round(r["overflow_minutes"], 1),
             "avg_wait_ci95": round(r["avg_wait_ci95"], 1), "share_meeting_target": round(r["share_meeting_target"], 2),
             "n_seeds": r["n_seeds"]} for r in study["results"]]
    return {"results": rows, "recommended": study["recommended"]}
