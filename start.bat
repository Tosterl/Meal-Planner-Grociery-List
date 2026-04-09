@echo off
title Meal Planner Pro
echo.
echo  ======================================
echo        Meal Planner Pro
echo  ======================================
echo.

:: Navigate to project folder
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed!
    echo  Download it from: https://www.python.org/downloads/
    echo  IMPORTANT: Check "Add Python to PATH" during install
    echo.
    pause
    exit /b 1
)

:: Check if .env exists
if not exist ".env" (
    echo  [WARNING] No .env file found!
    echo  Kroger search and some features won't work without it.
    echo  Create a file called .env in this folder with:
    echo.
    echo    KROGER_CLIENT_ID=your_client_id
    echo    KROGER_CLIENT_SECRET=your_client_secret
    echo.
    echo  Get credentials at: https://developer.kroger.com
    echo.
)

:: Use saved zip or ask for one
set "ZIP="
if exist ".zip_code" (
    set /p ZIP=<.zip_code
)

if not defined ZIP (
    set /p ZIP="  Enter your zip code (for Kroger store): "
    if defined ZIP (
        echo|set /p="%ZIP%"> .zip_code
        echo  Zip code saved for next time!
    )
)

echo.
echo  Opening Meal Planner in your browser...
echo.

:: Open the browser first
start "" "%~dp0index-pro.html"

:: Small delay so browser opens before server output floods the screen
timeout /t 2 >nul

echo  Starting API server on http://localhost:8099 ...
echo  Keep this window open while using the app.
echo  Close this window or press Ctrl+C to stop.
echo.
echo  ======================================
echo.

if defined ZIP (
    python api_server.py --zip %ZIP%
) else (
    python api_server.py
)

pause
