@echo off
REM Windows launcher for Duplicate Media Finder
REM Changes to project directory, starts Flask app, and opens browser

REM Get the directory where this batch file is located
cd /d "%~dp0"

REM Display startup message
echo Starting Duplicate Media Finder...
echo.
echo Flask server will start on http://127.0.0.1:5055
echo Browser will open automatically in a few seconds...
echo.
echo Press Ctrl+C to stop the server
echo.

REM Start browser opener in background (waits 3 seconds then opens browser)
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5055"

REM Start Flask app (this will keep the window open to show Flask output)
python app.py

