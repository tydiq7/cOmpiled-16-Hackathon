"""Seed data for the UCSD campus site.

Coordinates: Geisel Library and Price Center come from published sources; the rest
are estimated from map labels (within roughly 25 m). Good enough for the demo.
To refine one, right-click the spot in Google Maps and paste its numbers here.
"""
from math import asin, cos, radians, sin, sqrt

SITE = {"id": "ucsd", "name": "UCSD campus", "center_lat": 32.8801, "center_lng": -117.2340}

# (id, display name, lat, lng)
NODES = [
    ("price_center", "Price Center", 32.8799, -117.2370),
    ("geisel", "Geisel Library", 32.8811, -117.2375),
    ("library_walk", "Library Walk", 32.8802, -117.2374),
    ("jacobs_hall", "Jacobs Hall", 32.8818, -117.2351),
    ("warren_mall", "Warren Mall", 32.8811, -117.2348),
    ("atkinson_hall", "Atkinson Hall", 32.8825, -117.2347),
    ("warren_lecture", "Warren Lecture Hall", 32.8805, -117.2344),
    ("serf", "Engineering Research Facility", 32.8798, -117.2350),
    ("matthews_quad", "Matthews Quad", 32.8791, -117.2353),
    ("conrad_prebys", "Conrad Prebys Music Center", 32.8782, -117.2347),
    ("student_health", "Student Health Services", 32.8792, -117.2380),
    ("career_services", "Career Services Center", 32.8785, -117.2378),
    ("sun_god_lawn", "Sun God Lawn", 32.8787, -117.2401),
]

# pairs of node ids that connect by walkway; length is computed below
EDGE_PAIRS = [
    ("geisel", "library_walk"),
    ("library_walk", "price_center"),
    ("library_walk", "student_health"),
    ("student_health", "career_services"),
    ("student_health", "sun_god_lawn"),
    ("price_center", "matthews_quad"),
    ("price_center", "serf"),
    ("price_center", "warren_lecture"),
    ("matthews_quad", "serf"),
    ("matthews_quad", "conrad_prebys"),
    ("serf", "warren_mall"),
    ("warren_mall", "warren_lecture"),
    ("warren_mall", "jacobs_hall"),
    ("jacobs_hall", "atkinson_hall"),
    ("geisel", "jacobs_hall"),
]

# (bin id, node id, capacity in liters, starting fill %, fill rate in % per hour)
BINS = [
    ("b1", "price_center", 240, 20, 9),
    ("b2", "price_center", 240, 15, 8),
    ("b3", "geisel", 240, 25, 6),
    ("b4", "library_walk", 240, 30, 7),
    ("b5", "warren_mall", 240, 10, 5),
    ("b6", "jacobs_hall", 240, 18, 4),
    ("b7", "matthews_quad", 240, 22, 6),
    ("b8", "serf", 240, 12, 4),
    ("b9", "sun_god_lawn", 240, 8, 3),
]

# (dock id, node id, slots)
DOCKS = [("d1", "geisel", 2), ("d2", "warren_mall", 2)]

# (robot id, starting node id)
ROBOTS = [("r1", "geisel"), ("r2", "geisel"), ("r3", "warren_mall"), ("r4", "warren_mall")]


def _meters(a, b):
    """Straight-line walking distance between two lat/lng points (haversine)."""
    lat1, lng1, lat2, lng2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return round(2 * 6371000 * asin(sqrt(h)))


_pos = {n[0]: (n[2], n[3]) for n in NODES}
EDGES = [
    (f"e{i + 1}", a, b, _meters(_pos[a], _pos[b]))
    for i, (a, b) in enumerate(EDGE_PAIRS)
]

if __name__ == "__main__":
    print(f"{len(NODES)} nodes, {len(EDGES)} edges, {len(BINS)} bins, "
          f"{len(DOCKS)} docks, {len(ROBOTS)} robots")
    for e in EDGES:
        print(e)
