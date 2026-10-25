# Autonomous Waste Fleet

Simulated fleet of trash-collecting robots on the UCSD campus: bins report fill levels,
a dispatcher sends robots, and a supervisor catches stuck/looping/low-battery robots.
See SPEC.md for the full design.

## Run

Run these from the repo root (the folder that contains `app/` and `web/`):

    pip install -r requirements.txt
    python -m uvicorn app.main:app --port 8000

Then open **http://localhost:8000/** for the dashboard.

- API explorer: http://localhost:8000/docs
- Second venue (airport) data: http://localhost:8000/sites/airport/state
- Skip the startup fleet-sizing run (it takes a few minutes in the background): set `SWEEP_ON_START=0`
  (PowerShell: `$env:SWEEP_ON_START=0`).
- If port 8000 is busy, pick another (`--port 8001`) and change `API` near the top of the script in `web/index.html`.
