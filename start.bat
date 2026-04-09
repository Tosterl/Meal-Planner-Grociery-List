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
    echo  Create a file called .env in this folder with:
    echo.
    echo    KROGER_CLIENT_ID=your_client_id
    echo    KROGER_CLIENT_SECRET=your_client_secret
    echo.
    echo  Get credentials at: https://developer.kroger.com
    echo.
    echo  Starting without Kroger features...
    echo.
    timeout /t 3 >nul
)

:: Use saved zip or ask for one
if exist ".zip_code" (
    set /p ZIP=<.zip_code
    echo  Using saved zip code: %ZIP%
) else (
    set /p ZIP="  Enter your zip code (for Kroger store): "
    echo %ZIP%> .zip_code
    echo  Zip code saved for next time!
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

python api_server.py --zip %ZIP%

pause
