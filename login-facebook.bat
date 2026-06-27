@echo off
echo ========================================
echo  Facebook Login (one time / when logged out)
echo ========================================
cd /d "%~dp0"
if not exist "backend\venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
cd backend
if not exist ".env" copy .env.example .env

set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers
set FACEBOOK_LOGIN_MODE=1

call venv\Scripts\activate
python scripts\facebook_login_sync.py
pause
