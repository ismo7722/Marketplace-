@echo off
echo Starting Frontend Dashboard...
cd /d "%~dp0frontend"
if not exist "node_modules" call npm install
echo Frontend running at http://localhost:5173
npm run dev
