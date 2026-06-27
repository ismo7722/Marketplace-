@echo off
echo Starting Frontend Dashboard...
cd /d "%~dp0\..\frontend"
if not exist "node_modules" (
    echo Installing npm packages...
    call npm install
)
if not exist ".env" copy .env.example .env
echo Frontend running at http://localhost:5173
npm run dev
