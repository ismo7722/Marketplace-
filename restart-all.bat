@echo off
echo ========================================
echo  Clean restart - Backend + Frontend
echo ========================================
cd /d "%~dp0"

call stop-backend.bat

echo Stopping frontend (5173, 5174)...
for %%P in (5173 5174) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        echo   Killing PID %%a on port %%P
        taskkill /PID %%a /F >nul 2>&1
    )
)

ping -n 3 127.0.0.1 >nul

echo Starting backend (new window)...
start "FB Monitor Backend" cmd /k "%~dp0start-backend.bat"

ping -n 10 127.0.0.1 >nul

echo Starting frontend (new window)...
start "FB Monitor Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Keep both CMD windows open.
