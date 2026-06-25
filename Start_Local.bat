@echo off
echo ===================================================
echo   ISTE CERTIFICATE HUB - LOCAL DISPATCH ENGINE
echo ===================================================
echo.
echo [1] Checking Python Environment...
cd backend
if not exist ".venv\" (
    echo Creating virtual environment...
    python -m venv .venv
)
cd ..

echo [2] Starting Backend Server on Port 8000...
start cmd /k "cd backend && call .venv\Scripts\activate && pip install -r requirements.txt && uvicorn main:app --reload"

echo [3] Starting Frontend Server on Port 3001...
start cmd /k "cd frontend && npm install && npm run dev"

echo.
echo [!] Local servers are booting up!
echo [!] Please open your browser to: http://localhost:3001
echo.
echo Note: When running locally, the backend will use your Gmail App Password
echo to bypass all cloud restrictions, allowing you to email anyone!
echo.
pause
