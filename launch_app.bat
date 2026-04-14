@echo off
REM SafetyCulture Tools — Windows Launcher
REM Double-click this file to start the app in your browser.

cd /d "%~dp0"

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python is not installed.
    echo Download it from https://www.python.org/downloads/ and try again.
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Setting up virtual environment (first run only^)...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Install dependencies if needed
python -c "import streamlit" 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing dependencies (first run only^)...
    pip install -r requirements.txt --quiet
)

echo Starting SafetyCulture Tools...
echo The app will open in your browser. Close this window to stop it.
python -m streamlit run app/Home.py
