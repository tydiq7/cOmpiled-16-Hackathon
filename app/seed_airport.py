"""Second venue: an airport terminal (modeled loosely on San Diego International). Owned by the lead.

Coordinates are approximate -- this site exists to show the same backend running a different venue
with its own map, bins, robots and busy hours. Ids deliberately reuse b1/r1/d1/e1 from the campus
site to prove sites are isolated from each other.
"""
SITE = {"id": "airport", "name": "San Diego Airport, Terminal 2", "center_lat": 32.7338, "center_lng": -117.1965}

NODES = [
    ("departures_curb", "Departures Curb", 32.7350, -117.1975),
    ("arrivals_curb", "Arrivals Curb", 32.7346, -117.1985),
    ("baggage_claim", "Baggage Claim", 32.7343, -117.1978),
    ("security", "Security Checkpoint", 32.7339, -117.1972),
    ("food_court", "Food Court", 32.7336, -117.1966),
    ("lounge", "Airline Lounge", 32.7334, -117.1960),
    ("gate_a", "Gate Concourse A", 32.7331, -117.1956),
    ("gate_b", "Gate Concourse B", 32.7326, -117.1950),
    ("gate_c", "Gate Concourse C", 32.7340, -117.1953),
    ("service_dock", "Service Dock", 32.7345, -117.1962),
]

EDGES = [
    ("e1", "arrivals_curb", "baggage_claim"),
    ("e2", "baggage_claim", "security"),
    ("e3", "departures_curb", "security"),
    ("e4", "security", "food_court"),
    ("e5", "food_court", "lounge"),
    ("e6", "lounge", "gate_a"),
    ("e7", "gate_a", "gate_b"),
    ("e8", "food_court", "gate_c"),
    ("e9", "gate_c", "gate_a"),
    ("e10", "service_dock", "food_court"),
    ("e11", "service_dock", "gate_c"),
    ("e12", "baggage_claim", "departures_curb"),
]

# (id, node, capacity_l, start_fill_pct, fill_rate_pct_per_hr) -- airports fill faster than a campus
BINS = [
    ("b1", "food_court", 240, 25, 14),
    ("b2", "food_court", 240, 15, 13),
    ("b3", "security", 240, 30, 10),
    ("b4", "baggage_claim", 240, 20, 9),
    ("b5", "gate_a", 240, 10, 12),
    ("b6", "gate_b", 240, 18, 11),
    ("b7", "gate_c", 240, 22, 11),
    ("b8", "arrivals_curb", 240, 12, 7),
    ("b9", "departures_curb", 240, 8, 7),
]

DOCKS = [("d1", "service_dock", 2), ("d2", "gate_b", 1)]

ROBOTS = [("r1", "service_dock"), ("r2", "service_dock"), ("r3", "gate_b")]


def fill_multiplier(hour):
    """Flight banks: morning departures and the late-afternoon rush, quiet overnight."""
    if hour < 5:
        return 0.2
    if hour < 9:
        return 2.2   # morning departure bank
    if hour < 11:
        return 1.0
    if hour < 14:
        return 1.5
    if hour < 19:
        return 2.0   # evening bank
    return 0.8
