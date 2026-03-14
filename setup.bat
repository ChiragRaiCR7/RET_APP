@echo off
setlocal
REM RET v4 Quick Start Script for Windows
REM Aligns with documentation.md

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

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm was not found in PATH. Install Node.js 18+ first.
    pause
    exit /b 1
)

echo.
echo Step 1: Setting up Backend...
echo.

pushd backend

REM Check if venv exists
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create backend virtual environment.
        popd
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate backend virtual environment.
    popd
    pause
    exit /b 1
)

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    popd
    pause
    exit /b 1
)

echo Installing Python dependencies...
python -m pip install -e ".[dev]"
if errorlevel 1 (
    echo ERROR: Failed to install backend dependencies from pyproject.toml.
    popd
    pause
    exit /b 1
)

echo Installing async PostgreSQL driver...
python -m pip install asyncpg
if errorlevel 1 (
    echo ERROR: Failed to install asyncpg.
    popd
    pause
    exit /b 1
)

echo Initializing database...
python -m scripts.init_db --seed-demo
if errorlevel 1 (
    echo ERROR: Database initialization failed.
    popd
    pause
    exit /b 1
)

echo Applying database migrations...
python -m alembic upgrade head
if errorlevel 1 (
    echo.
    echo WARNING: Migration step reported an error.
    echo If this is a database that was created before alembic was introduced,
    echo run the following from the backend directory to stamp the current schema:
    echo   python -m alembic stamp head
    echo Then re-run setup.bat, or manually run:
    echo   python -m alembic upgrade head
    echo.
)

echo Backend setup complete!
echo.
echo To start backend, run:
echo   cd backend
echo   .\.venv\Scripts\activate.ps1
echo   python start.py
echo.

popd

echo.
echo Step 2: Setting up Frontend...
echo.

pushd frontend

if not exist "node_modules" (
    echo Installing Node.js dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: Frontend dependency installation failed.
        popd
        pause
        exit /b 1
    )
)

if exist "node_modules" (
    echo Verifying frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: Frontend dependency verification failed.
        popd
        pause
        exit /b 1
    )
)

echo Frontend setup complete!
echo.
echo To start frontend, run:
echo   cd frontend
echo   npm run dev
echo.

popd

echo.
echo ====================================
echo Setup Complete!
echo ====================================
echo.
echo Next steps:
echo   1. Start Backend (PowerShell Terminal 1):
echo      cd backend
echo      .\.venv\Scripts\Activate.ps1
echo      python start.py
echo.
echo   2. Start Frontend (PowerShell Terminal 2):
echo      cd frontend
echo      npm run dev
echo.
echo   3. Open browser:
echo      http://localhost:5173
echo.
echo   4. Open backend docs:
echo      http://localhost:8000/docs
echo.
echo   5. Login with:
echo      Username: admin
echo      Password: admin123
echo.
pause
