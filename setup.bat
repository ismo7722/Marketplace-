@echo off
echo ========================================
echo  Facebook Monitoring - Full Setup
echo  Python + Frontend + Chromium
echo ========================================
cd /d "%~dp0"

echo.
echo [1/5] Python virtual environment...
cd backend
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate
if not exist ".env" copy .env.example .env
if not exist "data" mkdir data
echo Installing Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo Python install failed.
    pause
    exit /b 1
)

echo.
echo [2/5] Database tables and defaults...
python -c "from app.config import get_settings; from app.startup_db import run_blocking_startup; run_blocking_startup(get_settings()); print('Database ready')"
if errorlevel 1 (
    echo Database init failed. Check DATABASE_URL in backend\.env
    pause
    exit /b 1
)

echo.
echo [3/5] Frontend npm packages...
cd ..\frontend
if not exist ".env" copy .env.example .env
call npm install
if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
)

echo.
echo [4/5] Playwright Chromium (~180 MB, required for monitoring)...
cd ..\backend
set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers
python scripts\ensure_playwright_chromium.py
if errorlevel 1 (
    echo Chromium install failed. Check internet and try again.
    pause
    exit /b 1
)

echo.
echo [5/5] Done.
echo.
echo ========================================
echo  Setup complete!
echo.
echo  1. Edit backend\.env  (ADMIN_EMAIL, ADMIN_PASSWORD, DATABASE_URL, SMTP)
echo  2. Double-click startall.bat
echo  3. Open http://localhost:5173
echo  4. Optional: login-facebook.bat if Facebook session is missing
echo ========================================
pause
