@echo off
echo ========================================
echo  Expose local backend for Vercel frontend
echo ========================================
echo.
echo 1. Run start-backend.bat first (port 8000)
echo 2. Keep this window open — copy the https URL shown below
echo 3. Vercel -^> Settings -^> Environment Variables
echo    BACKEND_URL = paste that https URL (no trailing slash)
echo 4. Redeploy frontend on Vercel
echo.
echo Starting tunnel to http://127.0.0.1:8000 ...
echo.
npx --yes localtunnel --port 8000
