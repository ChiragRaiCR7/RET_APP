@echo off
REM RET v4 Quick Start Script for Windows

echo.
echo ====================================
echo RET v4 - Local Development Setup
echo ====================================
echo.

REM Check if running from repo root
if not exist "backend" (
    echo ERROR: Please run this script from the repository root (D:\WORK\RET_App)
    pause
    exit /b 1
)

echo.
echo Step 1: Setting up Backend...
echo.

cd backend

REM Check if venv exists
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing Python dependencies...
pip install -q -r requirements.txt

echo Initializing database...
python -c "from api.core.database import init_db; init_db()" 2>nul

echo Backend setup complete!
echo.
echo To start backend, run:
echo   cd backend
echo   .\.venv\Scripts\activate.ps1
echo   uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
echo.

cd ..

echo.
echo Step 2: Setting up Frontend...
echo.

cd frontend

if not exist "node_modules" (
    echo Installing Node.js dependencies...
    call npm install
)

echo Frontend setup complete!
echo.
echo To start frontend, run:
echo   cd frontend
echo   npm run dev
echo.

cd ..

echo.
echo ====================================
echo Setup Complete!
echo ====================================
echo.
echo Next steps:
echo   1. Start Backend (PowerShell Terminal 1):
echo      cd backend
echo      .\.venv\Scripts\Activate.ps1
echo      uvicorn api.main:app --reload
echo.
echo   2. Start Frontend (PowerShell Terminal 2):
echo      cd frontend
echo      npm run dev
echo.
echo   3. Open browser:
echo      http://localhost:3000
echo.
echo   4. Login with:
echo      Username: admin
echo      Password: (check console output or scripts/create_admin.py)
echo.
pause
