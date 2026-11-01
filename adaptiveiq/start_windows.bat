@echo off
REM AdaptiveIQ - starts the model, the backend and the website, then opens the browser.
REM Folder layout expected:  adaptive-quiz\models\qwen7b-mcq-Q4_K_M.gguf
REM                          adaptive-quiz\llama\llama-server.exe
REM                          adaptive-quiz\adaptiveiq\   (this file is here)
REM The site works without the model (quizzes, analytics); only question generation needs it.
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\activate.bat" (echo [X] Run setup_windows.bat first. & pause & exit /b 1)
if not exist "frontend\node_modules" (echo [X] Run setup_windows.bat first. & pause & exit /b 1)

if not exist "..\models\qwen7b-mcq-Q4_K_M.gguf" goto nomodel
if not exist "..\llama\llama-server.exe" goto nomodel
echo Starting the AI model in window 1. Loading takes up to a minute...
start "1 - Qwen model (keep open)" cmd /k ""..\llama\llama-server.exe" -m "..\models\qwen7b-mcq-Q4_K_M.gguf" -c 4096 --port 8080"
goto backend
:nomodel
echo [!] Model or llama-server not found, so question generation will be offline. Everything else works.
:backend

echo Starting the backend in window 2 (it applies any new database migrations first)...
start "2 - Backend (keep open)" cmd /k "cd /d "%~dp0backend" && call .venv\Scripts\activate.bat && python -m alembic upgrade head && uvicorn app.main:app --port 8000"

echo Starting the website in window 3...
start "3 - Website (keep open)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo Waiting for everything to start...
timeout /t 12 /nobreak >nul
start "" http://localhost:5173

echo.
echo AdaptiveIQ is opening in your browser: http://localhost:5173
echo The badge at the top right says "Qwen 7B online" once the model has loaded.
echo Email verification links (when SMTP is not set up) appear in window 2.
echo To stop everything, close the windows.
pause
