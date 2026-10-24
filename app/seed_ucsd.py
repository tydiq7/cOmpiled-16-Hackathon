"""Campus seed data. OWNED BY TEAMMATE 1 -- this is a placeholder so the backend can run.

Teammate 1: replace the contents with 12-15 real UCSD spots, keeping these six
module-level names and these exact field names (db.reset_db() reads them).
"""

SITE = {"id": "ucsd", "name": "UCSD", "center_lat": 32.8801, "center_lng": -117.2340}

NODES = [
    {"id": "price_center", "name": "Price Center", "lat": 32.8797, "lng": -117.2362},
    {"id": "geisel", "name": "Geisel Library", "lat": 32.8811, "lng": -117.2376},
    {"id": "warren_mall", "name": "Warren Mall", "lat": 32.8826, "lng": -117.2340},
    {"id": "library_walk", "name": "Library Walk", "lat": 32.8805, "lng": -117.2370},
]

# length_m is computed from lat/lng by db.reset_db() when omitted
EDGES = [
    {"id": "e1", "from": "price_center", "to": "library_walk"},
    {"id": "e2", "from": "library_walk", "to": "geisel"},
    {"id": "e3", "from": "library_walk", "to": "warren_mall"},
]

BINS = [
    {"id": "b1", "node_id": "price_center", "capacity_l": 120, "fill_rate_pct_per_hr": 6.0},
    {"id": "b2", "node_id": "library_walk", "capacity_l": 120, "fill_rate_pct_per_hr": 5.0},
    {"id": "b3", "node_id": "warren_mall", "capacity_l": 120, "fill_rate_pct_per_hr": 4.0},
]

DOCKS = [
    {"id": "d1", "node_id": "geisel", "slots": 2},
]

ROBOTS = [
    {"id": "r1", "node_id": "geisel"},
    {"id": "r2", "node_id": "geisel"},
]
