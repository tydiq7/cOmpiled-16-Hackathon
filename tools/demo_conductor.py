"""Runs the demo for you: starts the day and triggers each event on a timeline while you screen-record
the dashboard and narrate. Plain Python, no installs. The server must already be running.

    python tools/demo_conductor.py            # 8 second countdown, then a 1:56 demo
    python tools/demo_conductor.py --delay 15 # longer countdown
    python tools/demo_conductor.py --fast     # 4x faster, just to check it works (do not record this)

It prints a cue line for every beat, so you can read it next to the voiceover script (DEMO_SCRIPT.md).
Two things it cannot do for you in the browser: show the fleet-sizing chart (zoom the page to 80% so it fits,
or scroll the sidebar) and pick the airport in the venue dropdown. Both are marked "YOU:" in the cues.
"""
import argparse
import json
import sys
import time
import urllib.request

API = "http://localhost:8000"


def call(method, path, body=None):
    data = json.dumps(body or {}).encode() if method == "POST" else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))


def get(path):
    return call("GET", path)


def post(path, body=None):
    return call("POST", path, body)


class Clock:
    def __init__(self, scale):
        self.t0, self.scale = time.monotonic(), scale

    def now(self):
        return time.monotonic() - self.t0

    def sleep(self, seconds):
        time.sleep(seconds * self.scale)


def sim_hour(state):
    t = state["sim_time"]  # 2026-10-24T12:15:00
    return int(t[11:13]) + int(t[14:16]) / 60


def wait_until_sim(clock, hour, max_real):
    """Wait until the sim clock reaches `hour`, but never longer than max_real seconds."""
    end = time.monotonic() + max_real * clock.scale
    while time.monotonic() < end and sim_hour(get("/state")) < hour:
        time.sleep(0.25)


def pick_robot(state, states=("EN_ROUTE", "COLLECTING"), skip=()):
    for r in state["robots"]:
        if r["id"] not in skip and r["online"] and r["route"] and r["state"] in states:
            return r
    return next((r for r in state["robots"] if r["id"] not in skip and r["online"]), state["robots"][0])


def wait_for_busy_robot(clock, skip=(), max_real=20):
    end = time.monotonic() + max_real * clock.scale
    while time.monotonic() < end:
        s = get("/state")
        r = next((r for r in s["robots"] if r["id"] not in skip and r["online"] and r["route"] and r["state"] == "EN_ROUTE"), None)
        if r:
            return s, r
        time.sleep(0.3)
    s = get("/state")
    return s, pick_robot(s, skip=skip)


def edge_near(state, node_id):
    """A walkway touching the robot's node: blocking it is likely to be on the robot's way."""
    return next((e for e in state["edges"] if node_id in (e["from"], e["to"]) and not e["blocked"]), state["edges"][0])


def cue(clock, text):
    print(f"[{int(clock.now() // 60):02d}:{int(clock.now() % 60):02d}] {text}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=int, default=8, help="countdown seconds before the demo starts")
    ap.add_argument("--fast", action="store_true", help="run 4x faster to test the script")
    args = ap.parse_args()
    scale = 0.25 if args.fast else 1.0

    try:
        post("/sim/pause"); post("/sites/airport/sim/pause")
    except Exception:
        sys.exit("The server is not running. Start it first:  python -m uvicorn app.main:app --port 8000")
    for site in ("", "/sites/airport"):
        post(site + "/sim/reset")
    post("/sim/speed", {"ticks_per_sec": 12})
    if not get("/analytics")["fleet_sizing"]:
        print("WARNING: the fleet-sizing chart is still empty (the startup sweep takes ~5 min). Wait, then rerun.")
    print("Dashboard reset to 8:00 AM. Open http://localhost:8000/ in Edge, full screen, campus venue.")
    print("Start your screen recording (Win+Alt+R) now.")
    for n in range(args.delay, 0, -1):
        print(f"  starting in {n}...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 30)

    clock = Clock(scale)

    def until(mark):
        """Sleep until `mark` seconds into the demo (a fixed timeline keeps the video under 2 minutes)."""
        remaining = mark * scale - clock.now()
        if remaining > 0:
            time.sleep(remaining)

    cue(clock, "BEAT 1  THE PROBLEM  (0:00-0:22)  Dashboard sits paused at 8 AM. Explain the problem.")
    until(22)

    cue(clock, "BEAT 2  START THE DAY + LUNCH RUSH  (0:22-0:44)  Bins turn yellow; robots leave only when needed.")
    post("/sim/speed", {"ticks_per_sec": 12})
    post("/sim/start")
    until(44)

    cue(clock, "BEAT 3  FAILURE 1: CROWD  (0:44-1:00)  Red CROWD badge on the map, then the reroute.")
    post("/sim/speed", {"ticks_per_sec": 6})
    s, r = wait_for_busy_robot(clock, max_real=8)
    edge = edge_near(s, r["node_id"])
    post("/faults/block_edge", {"edge_id": edge["id"], "minutes": 120})
    cue(clock, f"        blocked {edge['id']} near robot {r['id']}")
    until(60)

    cue(clock, "BEAT 4  FAILURE 2: STUCK ROBOT  (1:00-1:16)  STUCK, then NEEDS A HUMAN; bin reassigned; alert.")
    s, r2 = wait_for_busy_robot(clock, skip=(r["id"],), max_real=8)
    post("/faults/freeze_robot", {"robot_id": r2["id"]})
    cue(clock, f"        froze robot {r2['id']}")
    until(76)

    cue(clock, "BEAT 5  THE ANSWER  (1:16-1:26)  YOU: show the fleet-sizing chart (zoom 80% so it fits, else scroll the sidebar).")
    post("/sim/pause")
    until(86)

    cue(clock, "BEAT 6  SCALE  (1:26-1:38)  YOU: pick 'San Diego Airport' in the venue dropdown now.")
    post("/sites/airport/sim/speed", {"ticks_per_sec": 12})
    post("/sites/airport/sim/start")
    until(98)
    post("/sites/airport/sim/pause")

    cue(clock, "BEAT 7  IMPACT + VISION  (1:38-1:56)  Nothing moves. Explain the impact and what is simulated vs. real.")
    until(116)

    cue(clock, "DONE. Stop the recording now (total about 1:56).")


if __name__ == "__main__":
    main()
