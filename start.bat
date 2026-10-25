@echo off
rem Double-click to install, start the server and open the dashboard. Keep this window open while you demo.
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
if errorlevel 1 (echo Install failed. Is Python installed and on PATH? & pause & exit /b 1)
start "" cmd /c "timeout /t 10 /nobreak >nul & start http://localhost:8000/"
echo Starting the server on http://localhost:8000/  (Ctrl+C to stop)
python -m uvicorn app.main:app --port 8000
echo.
echo The server stopped. Scroll up for the error message.
pause
