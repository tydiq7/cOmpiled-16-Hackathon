"""Second venue: an airport terminal (modeled loosely on San Diego International). Owned by the lead.

Layout: landside (curbs, ticketing, baggage claim, rental cars), two security checkpoints, an airside
plaza, and three concourses of four gates each, with three service docks. Positions are approximate:
nodes are placed in metres east/north of the terminal center and converted to lat/lng. The point of
this site is to show the same backend running a very different venue -- its own map, bins, robots and
busy hours. Ids deliberately reuse b1/r1/d1/e1 from the campus site to prove sites are isolated.
"""
import math

SITE = {"id": "airport", "name": "San Diego Airport, Terminal 2", "center_lat": 32.7338, "center_lng": -117.1965}

_LAT0, _LNG0 = SITE["center_lat"], SITE["center_lng"]

# (id, display name, metres east, metres north of the terminal center)
_PLACES = [
    # landside
    ("departures_curb", "Departures Curb", -300, 120),
    ("arrivals_curb", "Arrivals Curb", -300, -40),
    ("shuttle_stop", "Shuttle Stop", -340, 40),
    ("rental_car", "Rental Car Center", -330, -140),
    ("ticketing_hall", "Ticketing Hall", -230, 100),
    ("baggage_claim_1", "Baggage Claim 1", -230, -20),
    ("baggage_claim_2", "Baggage Claim 2", -230, -90),
    ("tsa_a", "Security Checkpoint A", -150, 110),
    ("tsa_b", "Security Checkpoint B", -150, 40),
    # airside plaza
    ("central_plaza", "Central Plaza", -60, 70),
    ("food_court", "Food Court", -20, 100),
    ("shops", "Terminal Shops", -20, 40),
    ("restrooms_central", "Central Restrooms", -60, 10),
    ("lounge", "Airline Lounge", 20, 70),
    # concourse hubs (each has its own food and seating)
    ("a_hub", "Concourse A Hub", 70, 150),
    ("b_hub", "Concourse B Hub", 70, 70),
    ("c_hub", "Concourse C Hub", 70, -10),
    # service docks
    ("service_west", "Service Dock West", -190, -150),
    ("service_central", "Service Dock Central", 10, 0),
    ("service_east", "Service Dock East", 190, -60),
] + [
    (f"gate_{c}{n}", f"Gate {c.upper()}{n}", 70 + 70 * n, y)
    for c, y in (("a", 150), ("b", 70), ("c", -10)) for n in range(1, 5)
]

NODES = [
    (nid, name, round(_LAT0 + north / 111320, 6), round(_LNG0 + east / (111320 * math.cos(math.radians(_LAT0))), 6))
    for nid, name, east, north in _PLACES
]

_LINKS = [
    # landside
    ("departures_curb", "arrivals_curb"), ("departures_curb", "shuttle_stop"), ("arrivals_curb", "shuttle_stop"),
    ("departures_curb", "ticketing_hall"), ("arrivals_curb", "baggage_claim_1"),
    ("baggage_claim_1", "baggage_claim_2"), ("baggage_claim_1", "ticketing_hall"),
    ("shuttle_stop", "rental_car"), ("rental_car", "baggage_claim_2"),
    ("rental_car", "service_west"), ("baggage_claim_2", "service_west"), ("baggage_claim_1", "service_west"),
    ("ticketing_hall", "tsa_a"), ("ticketing_hall", "tsa_b"), ("tsa_a", "tsa_b"),
    # airside plaza
    ("tsa_a", "central_plaza"), ("tsa_b", "central_plaza"), ("central_plaza", "food_court"),
    ("central_plaza", "restrooms_central"), ("food_court", "shops"), ("shops", "lounge"),
    ("restrooms_central", "service_central"), ("service_central", "shops"),
    # into the concourses, with cross links so walkway blocks have detours
    ("food_court", "a_hub"), ("lounge", "b_hub"), ("service_central", "c_hub"),
    ("a_hub", "b_hub"), ("b_hub", "c_hub"),
    ("service_east", "gate_c2"), ("service_east", "gate_b2"),
] + [
    link
    for c in "abc"
    for link in [(f"{c}_hub", f"gate_{c}1")] + [(f"gate_{c}{n}", f"gate_{c}{n + 1}") for n in range(1, 4)]
]

EDGES = [(f"e{i + 1}", a, b) for i, (a, b) in enumerate(_LINKS)]

# (node, number of bins, capacity_l, base fill rate in % per hour): airports fill fast
_BIN_PLAN = [
    ("departures_curb", 2, 240, 14), ("arrivals_curb", 2, 240, 12), ("shuttle_stop", 1, 240, 9),
    ("rental_car", 1, 240, 8), ("ticketing_hall", 2, 240, 13), ("baggage_claim_1", 2, 240, 12),
    ("baggage_claim_2", 1, 240, 10), ("tsa_a", 2, 240, 18), ("tsa_b", 2, 240, 18),
    ("central_plaza", 1, 240, 14), ("food_court", 3, 240, 26), ("shops", 1, 240, 14),
    ("restrooms_central", 1, 240, 15), ("lounge", 1, 240, 10),
    ("a_hub", 2, 240, 22), ("b_hub", 2, 240, 22), ("c_hub", 2, 240, 22),
] + [(f"gate_{c}{n}", 1, 240, 16) for c in "abc" for n in range(1, 5)]

_RATE_SCALE = 0.6  # tuned so the fleet-sizing sweep recommends about 6 robots for this terminal
_START_FILL = (8, 14, 20, 26, 12, 18, 24, 10)  # staggered so the day doesn't start in lockstep
BINS = []
for _node, _count, _cap, _rate in _BIN_PLAN:
    for _ in range(_count):
        BINS.append((f"b{len(BINS) + 1}", _node, _cap, _START_FILL[len(BINS) % len(_START_FILL)], round(_rate * _RATE_SCALE, 1)))

DOCKS = [("d1", "service_west", 2), ("d2", "service_central", 2), ("d3", "service_east", 2)]

ROBOTS = [("r1", "service_west"), ("r2", "service_west"), ("r3", "service_central"),
          ("r4", "service_central"), ("r5", "service_east"), ("r6", "service_east")]


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
