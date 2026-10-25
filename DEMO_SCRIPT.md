# Demo recording: 2-minute voiceover script

Total length: about 1:56. About 22 s for the problem, about 18 s for impact and vision, and about 75 s of live demo in between.

## How to record

1. Server running (`start.bat` or `python -m uvicorn app.main:app --port 8000`), and the fleet-sizing chart already filled in (about 5 minutes after the server starts).
2. Open `http://localhost:8000/` in Edge, full screen, dark mode, campus venue. Set browser zoom to **80%** (Ctrl and minus) so the chart in the sidebar fits without scrolling. If it is still cut off, scroll the sidebar at beat 5.
3. Start the recording with `Win+Alt+R`.
4. In a terminal, from the repo root: `python tools/demo_conductor.py`. It counts down 8 seconds, then runs every event by itself and prints a cue line at the start of each beat.
5. Narrate while it runs. Stop the recording when it prints DONE.

Times are fixed marks, so the video stays under 2 minutes. The lines below are written to fit each beat at a normal speaking pace (about 150 words per minute).

## Voiceover

| Time | On screen | Say |
|---|---|---|
| **0:00-0:22** The problem | Dashboard paused at 8:00 AM. Bins green. | "Campus bins overflow at lunch, while crews empty half-full ones on a fixed schedule. That means litter, smells, and wasted trips. Nobody should have to open an app to fix it. This is the software brain for a fleet of autonomous trash robots, shown here as a live simulation of UCSD." |
| **0:22-0:44** Day starts, lunch rush | Clock runs; bins go yellow; robots leave docks; "planned route..." lines in the feed. | "A full day runs in about two minutes. Bins report how full they are, and robots stay docked until one needs emptying. At lunch, an optimizer plans multi-stop routes, so one robot clears several bins per trip. Every decision shows up in the feed." *(point at the feed)* |
| **0:44-1:00** Failure 1: crowd | Red pulsing "CROWD ... blocked" badge on a walkway; the feed says a robot rerouted. | "Failure one: a crowd blocks a walkway. It's flagged on the map, the robot reroutes, and the feed says why." |
| **1:00-1:16** Failure 2: stuck robot | A robot goes red: "STUCK", then "NEEDS A HUMAN". Toast and beep; the problems panel lists it. | "Failure two: a robot gets stuck. The supervisor retries, then escalates. Its bin goes to another robot and a human is alerted. The system knows when it's stuck." |
| **1:16-1:26** The answer | Sidebar chart: fleet size vs. wait. | "The question a customer cares about: how many robots? Seven keeps 95 percent of bins emptied within fifteen minutes." |
| **1:26-1:38** Scale | **You pick "San Diego Airport"** in the dropdown. A different map, 40 bins, 6 robots. | "And the same engine runs an airport, with its own map, bins, and busy hours. There, four robots is enough." |
| **1:38-1:56** Impact + vision | Nothing moves (stay on the airport, or switch back to campus). | "We believe this means cleaner venues, fewer wasted trips, and staff freed up for the real exceptions. Today everything is simulated; in the real world, cameras, GPS and fill sensors replace each piece. Robots self-unload at docks. We're a fleet-software company first." |

## Notes

- Do not describe how the docks work. Say only "robots self-unload at docks".
- Only say "a text goes out" if Twilio is set up. It is not on the demo machine, so the line says "a human is alerted".
- The chart numbers (7 campus, 4 airport) come from the startup sweep. Check the chart shows the same before you record, since the sweep can shift by a robot between runs.
- If you quote impact numbers (cost, emissions, litter), verify the source first. The lines above use "we believe" and no statistics.
- The signal-loss demo (a robot goes offline and reconnects) did not fit in 2 minutes. Mention it in Q&A if asked: it keeps working offline on a time-limited assignment, then syncs.
