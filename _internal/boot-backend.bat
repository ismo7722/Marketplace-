@echo off
echo ========================================
echo  Facebook Monitoring - Backend
echo ========================================
cd /d "%~dp0\.."

cd backend
if not exist "venv" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate
if not exist ".env" copy .env.example .env
if not exist "data" mkdir data
set PLAYWRIGHT_BROWSERS_PATH=%~dp0..\backend\playwright-browsers
echo.
echo Admin login from backend\.env (ADMIN_EMAIL / ADMIN_PASSWORD)
echo Local monitoring uses a visible Chromium window.
echo Starting server on port from backend\.env (API_PORT)...
echo.
python run.py
echo.
if errorlevel 1 (
    echo Backend exited with an error.
) else (
    echo Backend stopped.
)
pause
