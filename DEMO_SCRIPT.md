# Demo recording: voiceover script

How to record (about 3.5 minutes):

1. Server running (`start.bat` or `python -m uvicorn app.main:app --port 8000`). Wait until the fleet-sizing chart has data (about 5 minutes after the server starts).
2. Open `http://localhost:8000/` in Edge, full screen, dark mode, campus venue. Zoom to about 110%.
3. Start the recording with `Win+Alt+R`.
4. In a terminal: `python tools/demo_conductor.py`. It counts down 8 seconds, then runs every beat below by itself. It prints a cue line at the start of each beat.
5. Narrate while it runs. Stop the recording with `Win+Alt+R` when it prints DONE.

Times are approximate (a few seconds of drift is normal, since some beats wait for the sim clock). Read the lines in quotes.

| Approx. time | On screen | Voiceover |
|---|---|---|
| **0:00** BEAT 1 (about 20 s) | Dashboard paused at 8:00 AM. Bins green. | "Campus bins overflow at lunch, while crews empty half-full bins on a fixed schedule. Nobody should have to open an app to fix that. This is our software brain for a fleet of autonomous trash robots. Everything you'll see is a live simulation of UCSD, and a full day runs in about two minutes." |
| **0:20** BEAT 2 (about 25 s) | The day starts. The clock runs; bins go green to yellow; robots leave their docks one at a time. | "We press start at 8 AM. Bins report how full they are. Notice the robots don't patrol. They stay docked until a bin actually needs emptying." |
| **0:45** BEAT 3 (about 10 s) | Around noon. More yellow and red bins near Price Center. The feed fills with "planned route…" lines. | "Lunch rush. Bins near Price Center fill fast. An optimizer plans multi-stop routes, so one robot clears several bins in a single trip. Every decision is written to the feed, so the system explains itself." *(point at the feed)* |
| **0:55** BEAT 4 (about 25 s) | Slows down. A red pulsing "CROWD … blocked" badge appears on a walkway; its line turns red and animates. The feed says a robot rerouted. | "Failure one: a crowd blocks a walkway. It's flagged right on the map. The robot reroutes around it, and the feed says why. Nobody had to intervene." |
| **1:20** BEAT 5 (about 25 s) | A robot is frozen. Its label goes red: "STUCK", then "NEEDS A HUMAN". A toast and a beep. The problems panel (top right) lists it. | "Failure two: a robot gets stuck. The supervisor notices it has made no progress, tries to recover it, then escalates. Its bin is handed to another robot, and a human is alerted. That alert is what would go out by text." *(Only say "a text goes out" if Twilio is configured. Otherwise say "an alert goes to a human".)* |
| **1:50** BEAT 6 (about 30 s) | A robot turns purple: "SIGNAL LOST", with a dashed ring. Then it reconnects and the feed says "synced N offline actions". | "Bonus: a robot loses its connection. It doesn't stop. It finishes its assignment from offline instructions, and it never runs past a time limit, so it can't collide with a robot the server has reassigned. When it reconnects it catches up on what it missed." |
| **2:20** BEAT 7 (about 45 s) | Fast-forward to 8 PM, paused. **You scroll the sidebar to the fleet-sizing chart.** | "At the end of the day, the question a customer cares about: how many robots do they need? We simulate full days with different fleet sizes. The answer here is seven robots. That's the smallest fleet that keeps 95% of bins emptied within 15 minutes of filling up. Fewer than that and waits climb." |
| **3:05** BEAT 8 (about 25 s) | **You pick "San Diego Airport" in the dropdown.** A different map, 40 bins, 6 robots, running. | "And this isn't just a campus system. Here's the same backend running an airport terminal: its own map, its own bins and robots, its own busy hours. Every venue is isolated, so a new site is just a new map and a list of bins. For this airport the answer is four robots." |
| **3:30** Outro | Back to the campus, or your vision slide. | "Today everything is simulated. In the real world, cameras and lidar replace the crowd sensing, GPS and SLAM replace the map graph, and fill sensors replace the simulated bins. Robots self-unload at docks. We're a fleet-software company first." |

Do not describe how the docks work. Say only "robots self-unload at docks".
