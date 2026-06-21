@echo off
echo ========================================
echo  Local backend (dev only)
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
echo Production API: https://facebook-monitoring-t4py.onrender.com
echo Local API:      http://127.0.0.1:8000
echo.
start "FB Monitor Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate && set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers && python run.py"
pause
