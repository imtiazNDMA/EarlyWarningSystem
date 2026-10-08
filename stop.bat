@echo off
rem Stop the Early Warning System. Stored data is kept.

cd /d "%~dp0"

docker compose down
if errorlevel 1 (
    echo The platform could not be stopped. Is Docker running?
    exit /b 1
)
echo The platform is stopped. Stored data is kept; run start.bat to start it again.
