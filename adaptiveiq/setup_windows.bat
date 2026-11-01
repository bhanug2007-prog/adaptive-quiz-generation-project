@echo off
REM AdaptiveIQ - one-time setup on Windows. Double-click this file once.
REM Needs: Python 3.11+ and Node.js 22 LTS (22.12 or newer), both on PATH. PostgreSQL 16 is optional
REM (choose SQLite during setup for a quick local run). See README.md section 2.
cd /d "%~dp0"

where python >nul 2>nul || (echo [X] Python not found. Install Python 3.11+ from python.org and tick "Add python.exe to PATH". & pause & exit /b 1)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || (echo [X] Python 3.11 or newer is needed. & pause & exit /b 1)
where node >nul 2>nul || (echo [X] Node.js not found. Install the 22 LTS version from nodejs.org. & pause & exit /b 1)
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit(a>22||(a===22&&b>=12)?0:1)" || (echo [X] Node.js 22.12 or newer is needed. & pause & exit /b 1)

echo === 1/4 Backend: Python environment and packages ===
cd backend
if not exist .venv python -m venv .venv || (echo [X] Could not create the Python environment. & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || (echo [X] pip install failed. Check your internet connection. & pause & exit /b 1)

echo === 2/4 Backend settings (.env) ===
python -m scripts.configure_env || (echo [X] Could not write backend\.env & pause & exit /b 1)

echo === 3/4 Database tables ===
python -m alembic upgrade head || (echo [X] Could not create the tables. If you chose PostgreSQL, check that it is running, that the database exists, and the URL in backend\.env. & pause & exit /b 1)
cd ..

echo === 4/4 Frontend packages ===
cd frontend
call npm install || (echo [X] npm install failed. Check your internet connection. & pause & exit /b 1)
cd ..

echo.
if exist "..\models\qwen7b-mcq-Q4_K_M.gguf" (echo [OK] model found) else (echo [!] Put qwen7b-mcq-Q4_K_M.gguf in the folder ..\models\)
if exist "..\llama\llama-server.exe" (echo [OK] llama-server found) else (echo [!] Unzip llama.cpp ^(bin-win-cpu-x64 zip^) into the folder ..\llama\)
echo.
echo Setup finished. From now on, double-click start_windows.bat to run AdaptiveIQ.
pause
