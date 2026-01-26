@echo off
REM RET v4 Comprehensive Testing Runner
REM Automated setup and test execution

echo.
echo ========================================
echo RET v4 - Comprehensive Testing Suite
echo ========================================
echo.

setlocal enabledelayedexpansion

REM Check if running from repo root
if not exist "backend" (
    echo ERROR: Please run this script from the repository root (D:\WORK\RET_App)
    pause
    exit /b 1
)

echo Step 1: Backend Setup
echo -----------------

cd backend

REM Check if venv exists
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -q -r requirements.txt 2>nul

echo Initializing database...
python scripts/init_db.py 2>nul

echo Creating demo users...
python scripts/demo_users.py

echo.
echo Step 2: Backend Server
echo -----------------
echo Starting backend server on port 8000...
echo Press Ctrl+C in this window to stop the server when done testing.
echo.

start "RET Backend" cmd /k "cd /d %cd% && .venv\Scripts\activate.bat && uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"

REM Wait a bit for backend to start
timeout /t 5 /nobreak

cd ..

echo.
echo Step 3: Frontend Setup
echo -----------------

cd frontend

if not exist "node_modules" (
    echo Installing npm dependencies...
    call npm install
)

echo.
echo Step 4: Frontend Server
echo -----------------
echo Starting frontend development server on port 5173...
echo.

start "RET Frontend" cmd /k "cd /d %cd% && npm run dev"

REM Wait for frontend to start
timeout /t 3 /nobreak

cd ..

echo.
echo ========================================
echo Services Started!
echo ========================================
echo.
echo Frontend:  http://localhost:5173
echo Backend:   http://localhost:8000
echo Swagger:   http://localhost:8000/docs
echo.
echo Two new terminal windows should have opened above.
echo.
echo Next Steps:
echo 1. Open browser to http://localhost:5173
echo 2. Login with credentials from Step 1 output above
echo 3. Follow COMPREHENSIVE_TEST_GUIDE.md for testing
echo.
echo To run automated API tests (once services are running):
echo    python test_all_features.py
echo.
echo To view manual testing checklist:
echo    Open MANUAL_TESTING_CHECKLIST.md
echo.
echo Press any key to close this window...
pause
