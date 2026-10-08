@echo off
setlocal
rem Start the Early Warning System: database, API and web app.
rem Usage: start.bat [--no-browser]

cd /d "%~dp0"

if not defined EWS_WEB_PORT set "EWS_WEB_PORT=5173"
set "APP_URL=http://localhost:%EWS_WEB_PORT%"

where docker >nul 2>&1
if errorlevel 1 (
    echo Docker is not installed or not on PATH. Install Docker Desktop, then run this again.
    exit /b 1
)

rem Start Docker Desktop if its engine is not running yet
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKER_DESKTOP%" (
    echo Docker is not running. Start Docker Desktop, then run this again.
    exit /b 1
)
echo Starting Docker Desktop...
start "" "%DOCKER_DESKTOP%"
set /a WAITED=0

:wait_for_docker
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a WAITED+=3
if %WAITED% geq 180 (
    echo Docker did not start within 3 minutes.
    exit /b 1
)
goto wait_for_docker

:docker_ready
echo Building and starting the platform...
docker compose up -d --build
if errorlevel 1 (
    echo The platform failed to start. Run "docker compose logs" to see why.
    exit /b 1
)

echo Waiting for the app at %APP_URL% ...
set /a WAITED=0

:wait_for_app
curl -s -f -o nul "%APP_URL%/api/health"
if not errorlevel 1 goto app_ready
timeout /t 2 /nobreak >nul
set /a WAITED+=2
if %WAITED% geq 120 (
    echo The app did not become ready within 2 minutes. Run "docker compose logs" to see why.
    exit /b 1
)
goto wait_for_app

:app_ready

echo.
echo The platform is running at %APP_URL%
echo Run stop.bat to shut it down.

if /i not "%~1"=="--no-browser" start "" "%APP_URL%"
exit /b 0
