@echo off
echo Stopping backend worker...

if exist "backend\data\backend.pid" (
    for /f %%p in (backend\data\backend.pid) do (
        echo Killing saved backend PID %%p
        taskkill /PID %%p /F >nul 2>&1
    )
    del /f /q "backend\data\backend.pid" >nul 2>&1
)

for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%run_worker.py%%'" get ProcessId /format:list 2^>nul ^| findstr "="') do (
    echo Killing run_worker.py PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

for %%P in (8000 8001) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        echo Killing PID %%a on port %%P
        taskkill /PID %%a /F >nul 2>&1
    )
)

ping -n 4 127.0.0.1 >nul
echo Done.
