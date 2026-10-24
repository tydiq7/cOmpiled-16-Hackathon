"""Seed data for the UCSD campus site.

IMPORTANT: the coordinates below are approximate. Open Google Maps, right-click
each spot, copy its latitude and longitude, and paste over the numbers here.
"""
from math import asin, cos, radians, sin, sqrt

SITE = {"id": "ucsd", "name": "UCSD campus", "center_lat": 32.8801, "center_lng": -117.2340}

# (id, display name, lat, lng)
NODES = [
    ("price_center", "Price Center", 32.8797, -117.2362),
    ("geisel", "Geisel Library", 32.8811, -117.2376),
    ("library_walk", "Library Walk", 32.8804, -117.2369),
    ("warren_mall", "Warren Mall", 32.8826, -117.2341),
    ("jacobs_hall", "Jacobs Hall", 32.8817, -117.2352),
    ("student_services", "Student Services", 32.8786, -117.2370),
    ("bookstore", "Bookstore", 32.8790, -117.2354),
    ("peterson_hall", "Peterson Hall", 32.8800, -117.2395),
    ("center_hall", "Center Hall", 32.8785, -117.2342),
    ("york_hall", "York Hall", 32.8760, -117.2352),
    ("sun_god", "Sun God Lawn", 32.8832, -117.2393),
    ("eucalyptus_grove", "Eucalyptus Grove", 32.8787, -117.2403),
]

# pairs of node ids that connect by walkway; length is computed below
EDGE_PAIRS = [
    ("price_center", "library_walk"),
    ("library_walk", "geisel"),
    ("price_center", "bookstore"),
    ("price_center", "student_services"),
    ("library_walk", "jacobs_hall"),
    ("jacobs_hall", "warren_mall"),
    ("bookstore", "center_hall"),
    ("bookstore", "jacobs_hall"),
    ("center_hall", "york_hall"),
    ("geisel", "sun_god"),
    ("geisel", "peterson_hall"),
    ("peterson_hall", "eucalyptus_grove"),
    ("student_services", "eucalyptus_grove"),
]

# (bin id, node id, capacity in liters, starting fill %, fill rate in % per hour)
BINS = [
    ("b1", "price_center", 240, 20, 9),
    ("b2", "price_center", 240, 15, 8),
    ("b3", "geisel", 240, 25, 6),
    ("b4", "library_walk", 240, 30, 7),
    ("b5", "warren_mall", 240, 10, 5),
    ("b6", "jacobs_hall", 240, 18, 4),
    ("b7", "bookstore", 240, 22, 6),
    ("b8", "center_hall", 240, 12, 4),
    ("b9", "sun_god", 240, 8, 3),
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
