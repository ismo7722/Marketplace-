@echo off
echo ========================================
echo  Facebook Login (one time / when logged out)
echo ========================================
cd /d "%~dp0backend"
if not exist "venv" (
    echo Run install-chromium.bat first.
    pause
    exit /b 1
)
if not exist ".env" copy .env.example .env

set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers
set FACEBOOK_LOGIN_MODE=1

call venv\Scripts\activate
python scripts\facebook_login_sync.py
pause
