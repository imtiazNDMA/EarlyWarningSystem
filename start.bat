@echo off
setlocal

cd /d "%~dp0"

if not exist ".env" (
    echo [ERROR] Missing .env file.
    echo Create it from .env.example and configure the required values.
    exit /b 1
)

if not defined HOST set "HOST=0.0.0.0"
if not defined PORT set "PORT=5001"

if not exist ".venv\Scripts\waitress-serve.exe" (
    where uv >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] uv is required to install the application dependencies.
        echo Install uv from https://docs.astral.sh/uv/ and run this file again.
        exit /b 1
    )

    echo [INFO] Installing application dependencies...
    uv sync
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        exit /b 1
    )
)

".venv\Scripts\python.exe" "scripts\check_lm_studio.py"
".venv\Scripts\python.exe" "scripts\check_mongodb.py"
if errorlevel 1 exit /b 1

echo [INFO] Starting Early Warnings at http://%HOST%:%PORT%
".venv\Scripts\waitress-serve.exe" --listen="%HOST%:%PORT%" wsgi:app
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" echo [ERROR] Application exited with code %EXIT_CODE%.
exit /b %EXIT_CODE%
