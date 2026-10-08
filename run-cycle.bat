@echo off
rem Run one monitoring cycle now: fetch forecasts for every district and screen them.
rem The platform must be running (start.bat).

cd /d "%~dp0"

docker compose exec api python -m ews.cycles.service
if errorlevel 1 (
    echo The cycle could not be run. Is the platform running? Try start.bat first.
    exit /b 1
)
echo Cycle finished. Reload the app to see the result.
