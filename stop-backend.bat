@echo off
echo Stopping backend...

if exist "backend\data\backend.pid" (
    for /f %%p in (backend\data\backend.pid) do (
        echo Killing saved backend PID %%p
        taskkill /PID %%p /F >nul 2>&1
    )
    del /f /q "backend\data\backend.pid" >nul 2>&1
)

for %%P in (8000 8001) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        echo Killing PID %%a on port %%P
        taskkill /PID %%a /F >nul 2>&1
    )
)

ping -n 4 127.0.0.1 >nul
echo Done.
