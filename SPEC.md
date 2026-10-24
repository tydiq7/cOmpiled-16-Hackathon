# Autonomous Waste Fleet — Hackathon Software Spec

Oct 24, 2026 · @Bhupesh

**Teammates, start here:** read the Overview, then find your role in **Team plan and handoff**. When you open your AI, paste the Overview, Scope, your component spec, the **Interfaces** contracts, and **Instructions for any AI assistant**, then ask it to write your file.

## Overview

We are building the software brain for a fleet of autonomous trash-collecting robots: a live simulation where bins report their fill level, a dispatcher sends robots to empty them, and a supervisor catches robots that get stuck, run low on battery, or loop. Nobody opens an app; people just throw trash away.

- **Event:** c0mpiled-16 at UCSD, theme "Invisible Interfaces." Hacking runs until submissions are due at 6:30 PM; top 5 demo live at 7:45 PM.
- **Target tracks:** Dispatch (live data moving physical things) and Unsupervised (agents that run for hours and know when they are stuck, overspending, looping, or should stop).
- **Demo story:** a sped-up day on a map of UCSD. Bins fill around lunch, robots fan out, one robot gets blocked by a crowd and reroutes, another gets stuck and the system texts a human. A day of operations in about 2 minutes.
- **Constraints:** about 4 hours of build time; one Claude Pro plan for writing code; no LLM calls needed at runtime; no hardware.
- **IP note:** the gravity-fed docking design is a planned provisional patent. In the demo and slides, describe docks only as "robots self-unload at docks" and keep the mechanism out.

## Scope

Everything the judges see runs in software today; the physical robot pieces are simulated, and real-world sensing is a pitch slide.

| Component | Today | How |
| --- | --- | --- |
| Database of sites, bins, robots, docks | Built | SQLite |
| Dispatch server (who empties which bin) | Built | Greedy assignment first, then route plans from the optimizer |
| Route optimization | Built | OR-Tools vehicle routing with capacity and battery limits |
| Fleet sizing | Built | Headless sim runs with 2 to 8 robots; smallest fleet meeting the service target |
| Navigation | Built, on a map graph | Shortest path on a graph of campus walkways |
| Autonomy supervisor (stuck, looping, low battery, escalate) | Built | State machine + detectors |
| Live dashboard | Built | One web page with a map + fleet-sizing chart |
| Demand forecast for positioning and charging | Built if time allows | Per-bin, per-hour average fill rate |
| SMS escalation to a human | Built if time allows | Twilio trial, else on-screen alert |
| Bin placement optimization | Stretch, else pitch slide | Facility location on simulated demand |
| Bin fill sensors | Simulated | Fill rates that rise with time of day |
| Obstacle and person avoidance | Simulated | "Crowd" zones that block walkways and force a reroute |
| Real GPS/SLAM, lidar, camera vision | Pitch only | One slide: what replaces each simulated piece |
| Docking mechanism details | Pitch only, high level | Patent caution |

Stretch, only if everything above works by 5:30: a laptop webcam running a pretrained person detector (YOLO) that pauses one robot in the sim when someone walks into frame.

## System architecture

&#91;embedded content: system architecture · 8 components, 1 shared database\]

The dashboard only talks to the API, every component reads and writes the shared database, and the supervisor is the only part that reaches a human. The optimizer plans multi-stop routes for the dispatcher and runs the fleet-sizing sweep.

## Data model

Eight tables in one SQLite file; a site owns its map, bins, docks and robots, and every change is logged as an event.

| Table | Key fields | Notes |
| --- | --- | --- |
| `sites` | id, name, center\_lat, center\_lng | One site for the demo: UCSD campus |
| `nodes` / `edges` | node: id, site\_id, name, lat, lng · edge: from\_id, to\_id, length\_m, blocked (bool) | The walkway graph robots drive on; `blocked` is how crowds are simulated |
| `bins` | id, site\_id, node\_id, capacity\_l, fill\_pct, fill\_rate\_pct\_per\_hr, last\_emptied\_at, status | Status: ok, needs\_pickup, assigned, overflowing |
| `docks` | id, site\_id, node\_id, slots | Where robots unload and charge |
| `robots` | id, site\_id, current\_node\_id, state, battery\_pct, load\_pct, task\_id, last\_progress\_at | State values listed in the supervisor spec |
| `tasks` | id, bin\_id, robot\_id, created\_at, assigned\_at, completed\_at, status, attempts | Status: open, assigned, done, failed, escalated |
| `events` | id, ts, sim\_time, kind, robot\_id, bin\_id, data\_json | The log: telemetry, dispatches, reroutes, alerts. Feeds the dashboard feed and analytics |

Keep sim time separate from wall-clock time (`sim_time` column) so the demo can run a full day in minutes.

## Component specs

Eight components; the first four are the core and must work by 5:00 PM.

### 1. Simulator (the world)

- Tick-based loop: each tick advances sim time by a fixed step (for example 1 sim-minute). A speed setting controls ticks per real second.
- Map: 12 to 15 nodes on UCSD campus (e.g. Price Center, Geisel Library, Warren Mall, Library Walk), coordinates read off a map, connected by walkway edges.
- Bins: fill rate follows a time-of-day curve (busy at lunch and between classes), plus small random noise. Overflow above 100%.
- Robots: move along edges at a fixed speed, drain battery per meter and while idle, gain load when emptying a bin.
- Fault injection: functions to block an edge (crowd), freeze a robot (stuck), or spike battery drain. Exposed as dashboard buttons for the demo.

### 2. Dispatcher (who empties which bin)

- Trigger: a bin becomes `needs_pickup` when its sensor reports 80% full.
- Assignment, version 1 (build first, as the fallback): for each open task, pick the available robot with the lowest travel time, skipping robots whose battery or remaining capacity can't cover the trip plus the return to a dock.
- Assignment, version 2 (core): every few sim-minutes, ask the optimizer for multi-stop routes covering all open tasks plus bins about to need pickup, and hand each robot its route. If the solver fails or times out, fall back to version 1.
- After each route: robot heads to the nearest dock when load is over 85% or battery under 25%.

### 3. Navigation

- Shortest path on the walkway graph with `networkx` (Dijkstra or A\*), ignoring blocked edges.
- Replanning: when an edge on the current route becomes blocked, recompute from the robot's current node. If no route exists, the robot waits and the supervisor takes over.
- Pitch slide: real robots would use GPS plus SLAM (building a map while localizing) and lidar.

### 4. Autonomy supervisor (the Unsupervised track)

Every robot runs a state machine: `IDLE → EN_ROUTE → COLLECTING → RETURNING → UNLOADING → CHARGING → IDLE`, plus `STUCK` and `ESCALATED`.

| Detector | Rule | Action |
| --- | --- | --- |
| Stuck | No progress along route for N sim-minutes | Retry reroute; after 2 failures, reassign the task and escalate |
| Looping | Same few nodes revisited repeatedly without reaching the target | Stop the robot, reassign the task, escalate |
| Low battery | Battery can't cover trip + return to dock | Abort task, return to dock, reassign |
| Over budget | Fleet energy use or task attempts above a set limit | Pause new dispatches, alert a human |
| Overflow risk | Bin predicted to overflow with no robot able to reach it in time | Alert a human with the bin location |

Every action writes an event, so the dashboard shows the system explaining itself ("Robot 3 rerouted: Library Walk blocked").

### 5. Perception (simulated)

- Today: crowd zones block edges on a schedule (e.g. Library Walk at noon) and via a demo button. Robots never "see"; they react to blocked edges.
- Stretch: a webcam person detector that sets one edge to blocked while a person is in frame.
- Pitch slide: onboard cameras with a person-detection model, slowing or stopping near pedestrians.

### 6. Optimization and analytics (the math hook)

The goal is the fewest robots that keep a site clean. These are optimization problems (operations research), solved in this order: bins are fixed, routes are optimized, then the fleet is sized.

- **Route optimization (core):** a capacitated vehicle routing problem. Inputs: travel times from the walkway graph, bins needing pickup (plus bins over about 60% that are nearby), each robot's remaining capacity and battery, dock locations. Output: an ordered stop list per robot minimizing total travel. Solver: OR-Tools with a 1 to 2 second time limit.
- **Fleet sizing (core):** run the sim headless (no dashboard, as fast as possible) for one full day with 2, 3, ... 8 robots, same random seed. Record overflow minutes, average wait from 80% full to emptied, and distance driven. The answer is the smallest fleet that meets the service target (assumed: no bin waits over 15 minutes). Show it as one chart on the dashboard.
- **Demand forecast (if time allows):** learn each bin's fill rate per hour of day from logged readings. Used to park idle robots near upcoming hot spots and to schedule charging in quiet hours, not to replace the sensors.
- **Bin placement (stretch):** a facility location problem: choose bin locations among candidate nodes so every node with simulated foot traffic is within a set walking distance, then rerun fleet sizing. Pitch slide if not built.
- **KPIs on the dashboard:** robots needed, overflow minutes, average wait, distance per pickup.

### 7. Notifications

- Escalations send an SMS through a Twilio trial account (it can only text verified numbers, so verify a teammate's phone).
- Fallback: an alert banner and sound on the dashboard. Build the fallback first.

### 8. Dashboard

- One web page: map with nodes, edges (red when blocked), bins colored by fill level, robots as moving dots labeled with state.
- Side panel: live event feed, KPI numbers, speed slider, and fault buttons (block walkway, freeze robot, drain battery).
- Polls the server about every 500 ms, or uses a WebSocket if time allows.

## API endpoints

A small REST API is enough; the dashboard polls `/state` and everything else is a control.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/state` | Full snapshot: sim time, nodes, edges, bins, robots, open tasks, KPIs |
| GET | `/events?since=<id>` | New events for the live feed |
| POST | `/sim/start` · `/sim/pause` · `/sim/reset` | Control the simulation |
| POST | `/sim/speed` | Body: `{ "ticks_per_sec": 20 }` |
| POST | `/faults/block_edge` | Body: `{ "edge_id": ..., "minutes": 30 }` (simulated crowd) |
| POST | `/faults/freeze_robot` | Body: `{ "robot_id": ... }` (simulated stuck robot) |
| POST | `/faults/drain_battery` | Body: `{ "robot_id": ... }` |
| POST | `/bins/{id}/report` | A bin reports its fill level (how real sensors would call in) |
| GET | `/analytics` | KPIs and fleet-sizing results |

## Tech stack and repo structure

One Python process runs the server and the simulation loop; the frontend is a single HTML file.

- **Backend:** Python 3.11, FastAPI, Uvicorn. The sim loop runs as a background task inside the same process.
- **Database:** SQLite via the built-in `sqlite3` module (no ORM, to save time).
- **Graph and routing:** `networkx`; `ortools` for vehicle routing (core).
- **Analytics:** `pandas` for preprocessing fill events.
- **Frontend:** one `index.html` with Leaflet (map) loaded from a CDN, plain JavaScript polling `/state`.
- **Alerts:** `twilio` Python package, behind a flag so the app runs without it.

```
waste-fleet/
  README.md
  requirements.txt
  app/
    main.py          # FastAPI app + endpoints + starts sim loop
    db.py            # schema, seed data, queries
    seed_ucsd.py     # campus nodes, edges, bins, docks, robots
    sim.py           # tick loop, bin filling, robot movement, faults
    dispatcher.py    # task creation + robot assignment
    navigation.py    # shortest path + replanning
    supervisor.py    # state machine + detectors + escalation
    optimize.py      # OR-Tools routing, fleet sizing, KPIs
    notify.py        # Twilio SMS, with dashboard fallback
  web/
    index.html       # map + event feed + controls
```

## Build plan

A working end-to-end loop by 4:00 PM, the supervisor and demo faults by 5:00 PM, and a feature freeze at 5:45 PM so the last 45 minutes go to the demo and submission.

**Roles (adjust for team size):**

- **You (lead, Claude Pro):** backend core and integration.
- **Teammate 1:** dashboard and campus map data.
- **Teammate 2:** optimizer, then pitch deck and demo video.
- Full file ownership and workflow are in **Team plan and handoff** below.

| Time | Milestone | Done when |
| --- | --- | --- |
| 2:30 to 3:00 | Skeleton | Repo, schema, seed data load, `/state` returns JSON |
| 3:00 to 4:00 | Core loop | Bins fill, tasks get created, robots drive to bins and back, map shows it live |
| 4:00 to 5:00 | Autonomy | Supervisor states, stuck/loop/battery detectors, rerouting around blocked edges, fault buttons; OR-Tools routes replace greedy dispatch |
| 5:00 to 5:45 | Polish | Fleet-sizing sweep and chart, KPIs, SMS (or banner) alerts, event feed wording |
| 5:45 | Feature freeze | Only bug fixes after this |
| 5:45 to 6:20 | Demo prep | Rehearse script twice, record a backup screen video, push to GitHub |
| 6:30 | Submission due | Submission form, repo link, video |

If the core loop isn't working by 4:15, keep greedy dispatch, cut the demand forecast and SMS, and spend the time on the supervisor: it's the part the Unsupervised track judges.

## Team plan and handoff

Three people, one shared GitHub repo, and each person owns separate files, so nobody overwrites anyone else. Teammates on free AI plans copy code from their AI into their own files and commit it; the lead merges everything.

### Who owns what

| Person | Owns these files | Builds against | Tools |
| --- | --- | --- | --- |
| Lead | `app/main.py`, `db.py`, `sim.py`, `dispatcher.py`, `navigation.py`, `supervisor.py`, `notify.py` | Both contracts below | Claude Pro |
| Teammate 1: dashboard + map data | `web/index.html`, `app/seed_ucsd.py` | `sample_state.json` (Contract 1) until the real server runs | Any free AI; Google Maps for coordinates |
| Teammate 2: optimizer + pitch | `app/optimize.py`; slides, demo script, backup video (outside the repo) | Contract 2, with made-up test data | Any free AI; Google Slides or similar |

**Teammate 1 tasks, in order:**

1. By hand: pick 12 to 15 UCSD spots (Price Center, Geisel Library, Warren Mall, Library Walk, etc.), copy each one's latitude and longitude from Google Maps, and list which spots connect by walkway. Put them in `seed_ucsd.py` as plain Python lists: nodes, edges, bins (one or two per busy spot), two docks, four robots.
2. With AI: build `web/index.html` as one file: Leaflet map, bins colored by `fill_pct`, robots as dots moving by `lat`/`lng`, blocked edges in red, live event feed, KPI numbers, speed slider, fault buttons, and a fleet-sizing chart from `fleet_sizing`. It reads `sample_state.json` first, then switches to polling `GET /state` every 500 ms.

**Teammate 2 tasks, in order:**

1. With AI: write `plan_routes` in `optimize.py` with Google OR-Tools, exactly matching Contract 2. Test it with the example data in the contract.
2. With AI: write `fleet_size_sweep` in the same file. Test it with a fake run function that returns made-up numbers.
3. From 4:30: slides (problem, live demo, simulated vs. real, robots self-unload at docks, fleet-sizing result, team), the demo script, and a backup screen recording of a clean run.

### GitHub workflow

1. Lead creates the repo `waste-fleet` with the file skeleton from Tech stack and repo structure, commits `sample_state.json`, and adds both teammates as collaborators (repo Settings, Collaborators).
2. Everyone clones it. Not comfortable with git? Use GitHub Desktop or VS Code's source control panel, or edit and commit your file directly on github.com.
3. Only edit files you own. Need a change in someone else's file? Ask them.
4. Pull before you push. Commit small and often, each time something works.
5. Fallback if git breaks: send your file in the group chat and the lead drops it in.

**Integration checkpoints:** 4:00 PM, lead wires `optimize.py` into the dispatcher and points `index.html` at the real `/state`. 5:00 PM, full run together. 5:45 PM, feature freeze.

### Using free AI plans

- Paste only the sections you need, not the whole doc: Overview, Scope, your component spec, Interfaces, and Instructions for any AI assistant.
- One file per chat. Ask for one piece at a time ("write the map and bin markers first"), test it, then ask for the next.
- If the chat gets long or slow, start a new one and paste the sections plus your current file.
- If the AI's code doesn't match the contract (different field names, different function arguments), make it fix that before anything else.

### Interfaces

These two contracts are fixed. Field names, function names and argument order don't change without telling the whole team.

**Contract 1: `GET /state` response** (also saved as `sample_state.json`; coordinates are approximate examples)

```json
{
  "sim_time": "2026-10-24T12:15:00",
  "running": true,
  "speed": 20,
  "nodes": [
    {"id": "price_center", "name": "Price Center", "lat": 32.8797, "lng": -117.2362},
    {"id": "geisel", "name": "Geisel Library", "lat": 32.8811, "lng": -117.2376}
  ],
  "edges": [
    {"id": "e1", "from": "price_center", "to": "geisel", "length_m": 220, "blocked": false}
  ],
  "bins": [
    {"id": "b1", "node_id": "price_center", "fill_pct": 82.5, "status": "needs_pickup"}
  ],
  "docks": [
    {"id": "d1", "node_id": "geisel", "slots": 2}
  ],
  "robots": [
    {"id": "r1", "lat": 32.8804, "lng": -117.2369, "node_id": "geisel", "state": "EN_ROUTE",
     "battery_pct": 64, "load_pct": 30, "route": ["b1"]}
  ],
  "events": [
    {"id": 101, "sim_time": "2026-10-24T12:14:00", "kind": "reroute", "message": "Robot r1 rerouted: Library Walk blocked"}
  ],
  "kpis": {"robots_active": 4, "overflow_minutes": 0, "avg_wait_min": 6.2, "distance_per_pickup_m": 410},
  "fleet_sizing": [
    {"robots": 2, "avg_wait_min": 31.0, "max_wait_min": 74.0, "overflow_minutes": 95},
    {"robots": 3, "avg_wait_min": 14.5, "max_wait_min": 29.0, "overflow_minutes": 12}
  ]
}
```

Values: bin `status` is one of `ok`, `needs_pickup`, `assigned`, `overflowing`. Robot `state` is one of `IDLE`, `EN_ROUTE`, `COLLECTING`, `RETURNING`, `UNLOADING`, `CHARGING`, `STUCK`, `ESCALATED`. Robot `lat`/`lng` is its live position between nodes, so the map can animate it. `fleet_sizing` is empty until the sweep has run.

**Contract 2: `app/optimize.py`**

```python
def plan_routes(nodes, travel_min, robots, stops, time_limit_s=2.0):
    """Assign bins to robots and order each robot's stops to minimize total travel time.

    nodes:      list[str]          node ids; row/column i of travel_min is nodes[i]
    travel_min: list[list[float]]  travel_min[i][j] = minutes from nodes[i] to nodes[j]
    robots:     list[dict]         {"id": "r1", "start": "geisel", "end": "geisel",
                                    "capacity_left": 70, "max_minutes": 45}
                                   start = robot's current node, end = dock node it returns to,
                                   capacity_left = percent of load it can still take,
                                   max_minutes = travel its battery can still cover
    stops:      list[dict]         {"bin_id": "b1", "node": "price_center", "demand": 30}
                                   demand = percent of robot capacity this bin will fill
    returns:    dict               {"routes": {"r1": ["b1", "b4"], "r2": []},
                                    "unassigned": ["b7"]}
                                   each robot's bins in visiting order; bins that can't fit go
                                   in unassigned instead of raising an error
    """


def fleet_size_sweep(run_fn, sizes=range(2, 9), target_max_wait_min=15.0, seed=42):
    """Find the smallest fleet that meets the service target.

    run_fn(num_robots, seed) -> {"avg_wait_min": float, "max_wait_min": float,
                                 "overflow_minutes": float}
        provided by the lead (a headless run of sim.py); use a fake for testing
    returns: {"results": [{"robots": 2, "avg_wait_min": ..., "max_wait_min": ...,
                           "overflow_minutes": ...}, ...],
              "recommended": 4}   smallest size with max_wait_min <= target, or None
    """
```

Test data for `plan_routes`: 4 nodes `["dock", "a", "b", "c"]` with travel times of 3 to 10 minutes between each pair, two robots starting and ending at `"dock"` with `capacity_left` 60 and `max_minutes` 40, and three stops with demand 30 each. Expect every stop assigned, no robot over 60 capacity.

## Demo script

Three minutes, built around two live failures the system handles on its own.

1. **Problem (20 s):** campus bins overflow at lunch while crews empty half-full bins on a fixed schedule. Nobody should have to open an app to fix that.
2. **Start the day (30 s):** hit start at 8 AM sim time, speed up. Bins go from green to yellow; robots leave the docks only when bins need them.
3. **Lunch rush (30 s):** bins near Price Center fill fast; the optimizer plans multi-stop routes so one robot clears several bins per trip. Point at the event feed explaining each decision.
4. **Failure 1, crowd (30 s):** click "block Library Walk." The walkway turns red, the robot reroutes, feed says why.
5. **Failure 2, stuck robot (30 s):** click "freeze Robot 2." The supervisor detects no progress, reassigns its task, and a teammate's phone gets a text. Hold the phone up.
6. **End of day (20 s):** show the fleet-sizing chart: the smallest fleet that keeps every bin under a 15-minute wait, plus distance per pickup.
7. **Vision (20 s):** one slide on what's simulated today vs. real hardware (cameras, GPS, self-unloading docks), and why this is a fleet-software company first.

Record a backup screen video of a clean run in case the live demo breaks.

## Instructions for any AI assistant

Paste this section along with the spec when you start a build session.

- Build in the order of the Build plan; get the end-to-end loop (sim → dispatcher → navigation → `/state` → map) working before adding anything else.
- Keep it minimal: plain Python, the stack listed above, no extra frameworks or services. Ask before adding a dependency.
- No LLM calls at runtime. Dispatch, routing and the supervisor are deterministic code.
- Write one file at a time, in small pieces we can test immediately. Include a quick way to run and check each piece.
- Every robot decision writes a human-readable event ("Robot 3 rerouted: Library Walk blocked"); the event feed is part of the demo.
- Make faults (block edge, freeze robot, drain battery) easy to trigger from the API and the dashboard.
- The app must run with Twilio unset; alerts fall back to the dashboard.
- Don't describe or model the internals of the docking mechanism; docks are just nodes where robots unload and charge.
- When something is ambiguous, pick the simplest option that keeps the demo working and say what you picked.
