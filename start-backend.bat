@echo off
echo ========================================
echo  Facebook Marketplace Monitor
echo ========================================
cd /d "%~dp0"

call stop-backend.bat

cd backend
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)
if not exist ".env" copy .env.example .env

set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers

echo.
echo Dashboard: https://facebook-monitoring.vercel.app
echo Backend:   http://127.0.0.1:8000
echo.
echo Starting backend (new window)...
start "FB Monitor Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate && set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers && python run.py"

ping -n 8 127.0.0.1 >nul

echo Starting tunnel for Vercel (new window)...
echo Copy the https URL into Vercel BACKEND_URL if it changed, then redeploy.
start "FB Monitor Tunnel" cmd /k "cd /d "%~dp0" && npx --yes localtunnel --port 8000"

echo.
echo Keep both windows open while using the live dashboard.
echo Run stop-backend.bat to stop the backend.
pause
