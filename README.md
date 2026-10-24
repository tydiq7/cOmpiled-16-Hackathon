# Autonomous Waste Fleet

Simulated fleet of trash-collecting robots on the UCSD campus: bins report fill levels,
a dispatcher sends robots, and a supervisor catches stuck/looping/low-battery robots.
See SPEC.md for the full design.

## Run

    pip install -r requirements.txt
    uvicorn app.main:app --reload

Then open http://localhost:8000/state (dashboard: web/index.html).
