"""Seed data for the UCSD campus site.

Coordinates: Geisel Library and Price Center come from published sources; the rest are
estimated from map labels (within roughly 25 m), which is fine for the demo.
To refine one, right-click the spot in Google Maps and paste its numbers here.
"""
import random
from math import asin, cos, radians, sin, sqrt

SITE = {"id": "ucsd", "name": "UCSD campus", "center_lat": 32.8801, "center_lng": -117.2340}

# One row per building:
# (id, name, lat, lng, foot traffic 1-5, number of bins, base fill rate in % per hour)
# Busy places get many bins that fill fast; quiet places get one or two that fill slowly.
BUILDINGS = [
    ("price_center",         "Price Center",                  32.8799, -117.2370, 5, 26, 16),
    ("geisel",               "Geisel Library",                32.8811, -117.2375, 5, 20, 12),
    ("library_walk",         "Library Walk",                  32.8802, -117.2374, 4, 12, 10),
    ("warren_mall",          "Warren Mall",                   32.8811, -117.2348, 4, 12, 9),
    ("trolley_station",      "Central Campus Trolley Station", 32.8792, -117.2320, 4, 8, 9),
    ("matthews_quad",        "Matthews Quad",                 32.8791, -117.2353, 3, 8, 7),
    ("jacobs_hall",          "Jacobs Hall",                   32.8818, -117.2351, 3, 8, 7),
    ("warren_lecture",       "Warren Lecture Hall",           32.8805, -117.2344, 3, 8, 7),
    ("sun_god_lawn",         "Sun God Lawn",                  32.8787, -117.2401, 3, 8, 6),
    ("engineering_2",        "Engineering Building II",       32.8812, -117.2339, 3, 8, 6),
    ("cognitive_science",    "Cognitive Science Building",    32.8806, -117.2393, 3, 8, 6),
    ("student_health",       "Student Health Services",       32.8792, -117.2380, 3, 6, 6),
    ("structural_materials", "Structural and Materials Engineering", 32.8798, -117.2331, 3, 6, 6),
    ("brennan_hall",         "Brennan Hall",                  32.8827, -117.2326, 3, 6, 6),
    ("social_sciences",      "Social Sciences Research Building", 32.8806, -117.2401, 3, 5, 6),
    ("douglas_hall",         "Douglas Hall",                  32.8833, -117.2333, 2, 5, 5),
    ("brown_hall",           "Brown Hall",                    32.8835, -117.2323, 2, 5, 5),
    ("black_hall",           "Black Hall",                    32.8821, -117.2328, 2, 5, 5),
    ("atkinson_hall",        "Atkinson Hall",                 32.8825, -117.2347, 2, 4, 4),
    ("serf",                 "Engineering Research Facility", 32.8798, -117.2350, 2, 4, 4),
    ("conrad_prebys",        "Conrad Prebys Music Center",    32.8782, -117.2347, 2, 4, 4),
    ("franklin_antonio",     "Franklin Antonio Hall",         32.8835, -117.2349, 2, 4, 3),
    ("canyonview",           "Canyonview Aquatic Center",     32.8806, -117.2322, 2, 4, 4),
    ("career_services",      "Career Services Center",        32.8785, -117.2378, 2, 3, 4),
    ("coalition",            "Coalition",                     32.8820, -117.2400, 2, 3, 4),
    ("umoja",                "Umoja",                         32.8825, -117.2394, 2, 3, 4),
    ("alianza",              "Alianza",                       32.8831, -117.2397, 2, 3, 4),
    ("faculty_club",         "Faculty Club",                  32.8793, -117.2394, 1, 2, 2),
]

NODES = [(b[0], b[1], b[2], b[3]) for b in BUILDINGS]      # (id, name, lat, lng)
TRAFFIC = {b[0]: b[4] for b in BUILDINGS}                  # foot traffic 1 (quiet) to 5 (very busy)

# Pairs of node ids that connect by walkway; length is computed below.
EDGE_PAIRS = [
    ("geisel", "library_walk"), ("library_walk", "price_center"),
    ("library_walk", "student_health"), ("library_walk", "cognitive_science"),
    ("student_health", "career_services"), ("student_health", "sun_god_lawn"),
    ("cognitive_science", "faculty_club"), ("faculty_club", "sun_god_lawn"),
    ("cognitive_science", "social_sciences"), ("social_sciences", "coalition"),
    ("coalition", "umoja"), ("umoja", "alianza"), ("geisel", "umoja"),
    ("price_center", "matthews_quad"), ("price_center", "serf"),
    ("price_center", "warren_lecture"), ("matthews_quad", "serf"),
    ("matthews_quad", "conrad_prebys"), ("serf", "warren_mall"),
    ("serf", "structural_materials"), ("structural_materials", "trolley_station"),
    ("structural_materials", "canyonview"), ("canyonview", "engineering_2"),
    ("warren_mall", "warren_lecture"), ("warren_mall", "jacobs_hall"),
    ("warren_mall", "engineering_2"), ("engineering_2", "warren_lecture"),
    ("engineering_2", "black_hall"), ("black_hall", "brennan_hall"),
    ("brennan_hall", "douglas_hall"), ("douglas_hall", "brown_hall"),
    ("brown_hall", "brennan_hall"), ("douglas_hall", "franklin_antonio"),
    ("jacobs_hall", "atkinson_hall"), ("atkinson_hall", "franklin_antonio"),
    ("geisel", "jacobs_hall"),
]

# How busy campus is at each hour of the day (index 0 = midnight). The sim multiplies a
# bin's base rate by this number, so bins fill fastest at lunch and between classes.
HOURLY_CURVE = [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.1, 0.3, 0.6, 0.9, 1.0, 1.2,
                1.8, 1.6, 1.1, 1.0, 0.8, 0.7, 0.8, 0.5, 0.4, 0.3, 0.2, 0.1]


def fill_rate_now(bin_rate_pct_per_hr, sim_hour):
    """Fill rate right now, in % per hour, for a bin at the given hour of the day."""
    return bin_rate_pct_per_hr * HOURLY_CURVE[int(sim_hour) % 24]


# (bin id, node id, capacity in liters, starting fill %, base fill rate in % per hour)
# Each bin gets its own starting fill and its own rate (building rate +/- 25%).
# The seed is fixed so every run, and every fleet-sizing run, starts the same.
_rng = random.Random(7)
BINS = []
for _id, _name, _lat, _lng, _traffic, _count, _rate in BUILDINGS:
    assert _count >= 1, f"{_name} needs at least one bin"
    for _ in range(_count):
        BINS.append((f"b{len(BINS) + 1}", _id, 240 if _traffic >= 3 else 120,
                     _rng.randint(5, 35), round(_rate * _rng.uniform(0.75, 1.25), 1)))

# (dock id, node id, slots)
# Spread across campus so an idle robot is never far from a bin: a single dock on the west side
# left the north-east corner about ten minutes away.
DOCKS = [("d1", "geisel", 3), ("d2", "price_center", 3), ("d3", "warren_mall", 3),
         ("d4", "brennan_hall", 3), ("d5", "trolley_station", 3)]

# Fleet-sizing sweep: with ~200 bins a handful of robots cannot keep up, so try 12 to 15 robots first
# and, if none meets the service target, keep going up to 20.
SWEEP_SIZES = range(12, 16)
SWEEP_MAX = 20

# (robot id, starting node id): 14 robots spread over the docks
ROBOTS = [(f"r{i + 1}", DOCKS[i % len(DOCKS)][1]) for i in range(14)]


def _meters(a, b):
    """Straight-line walking distance between two lat/lng points (haversine)."""
    lat1, lng1, lat2, lng2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return round(2 * 6371000 * asin(sqrt(h)))


_pos = {n[0]: (n[2], n[3]) for n in NODES}
EDGES = [(f"e{i + 1}", a, b, _meters(_pos[a], _pos[b])) for i, (a, b) in enumerate(EDGE_PAIRS)]

if __name__ == "__main__":
    print(f"{len(NODES)} nodes, {len(EDGES)} edges, {len(BINS)} bins, "
          f"{len(DOCKS)} docks, {len(ROBOTS)} robots")
    for b in BUILDINGS:
        n = sum(1 for x in BINS if x[1] == b[0])
        print(f"  {b[1]:<38} traffic {b[4]}  bins {n}  base rate {b[6]}%/hr")
