"""Site registry. A site is a venue (campus, airport, mall...) described by a seed module.

To add a venue: write app/seed_<name>.py with SITE, NODES, EDGES, BINS, DOCKS, ROBOTS (tuple or dict
rows, see below), optionally a fill_multiplier(hour) function for that venue's busy hours, and add
the module to MODULES. Nothing else in the backend changes.

  NODES  (id, name, lat, lng)                 or {"id","name","lat","lng"}
  EDGES  (id, from, to[, length_m])           or {"id","from","to"[,"length_m","name"]}
  BINS   (id, node_id, capacity_l[, start_fill_pct[, fill_rate_pct_per_hr]])
         or {"id","node_id","capacity_l","fill_rate_pct_per_hr"[,"start_fill_pct"]}
  DOCKS  (id, node_id, slots)                 or dict
  ROBOTS (id, node_id)                        or dict

Optional per-venue tuning, all read with getattr so a seed file can leave them out:
  fill_multiplier(hour)  or  HOURLY_CURVE (24 numbers)   -> the venue's busy hours
  SWEEP_SIZES            -> fleet sizes the fleet-sizing sweep tries first (default 2..8)
  SWEEP_MAX              -> if none of those meets the target, keep trying up to this many robots
"""
import math
from dataclasses import dataclass

from . import seed_airport, seed_ucsd

MODULES = [seed_ucsd, seed_airport]


def haversine_m(a, b):
    r = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@dataclass
class Site:
    id: str
    name: str
    center_lat: float
    center_lng: float
    nodes: list
    edges: list
    bins: list
    docks: list
    robots: list
    fill_multiplier: object = None  # optional hour -> multiplier; None means the default curve
    sweep_sizes: tuple = tuple(range(2, 9))
    sweep_max: int = None


def _row(row, keys):
    return dict(row) if isinstance(row, dict) else dict(zip(keys, row))


def _curve(mod):
    """The venue's busy-hours function: its own fill_multiplier, else its HOURLY_CURVE table, else None."""
    if getattr(mod, "fill_multiplier", None):
        return mod.fill_multiplier
    curve = getattr(mod, "HOURLY_CURVE", None)
    return (lambda hour: curve[int(hour) % 24]) if curve else None


def load(mod):
    nodes = [_row(n, ("id", "name", "lat", "lng")) for n in mod.NODES]
    pos = {n["id"]: n for n in nodes}
    edges = []
    for e in mod.EDGES:
        e = _row(e, ("id", "from", "to", "length_m"))
        e["length_m"] = e.get("length_m") or round(haversine_m(pos[e["from"]], pos[e["to"]]), 1)
        edges.append(e)
    bins = []
    for b in mod.BINS:
        b = _row(b, ("id", "node_id", "capacity_l", "start_fill_pct", "fill_rate_pct_per_hr"))
        b.setdefault("start_fill_pct", None)
        bins.append(b)
    s = mod.SITE
    return Site(id=s["id"], name=s["name"], center_lat=s["center_lat"], center_lng=s["center_lng"],
                nodes=nodes, edges=edges, bins=bins,
                docks=[_row(d, ("id", "node_id", "slots")) for d in mod.DOCKS],
                robots=[_row(r, ("id", "node_id")) for r in mod.ROBOTS],
                fill_multiplier=_curve(mod),
                sweep_sizes=tuple(getattr(mod, "SWEEP_SIZES", range(2, 9))),
                sweep_max=getattr(mod, "SWEEP_MAX", None))


SITES = {s.id: s for s in (load(m) for m in MODULES)}
DEFAULT_SITE_ID = load(seed_ucsd).id


def get(site_id):
    return SITES[site_id]
