@echo off
setlocal EnableDelayedExpansion
title PrepPilot - Agentic AI Placement Assistant
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto nopython

if exist ".venv\Scripts\python.exe" goto haveenv
echo Creating a private Python environment for PrepPilot. This happens only the first time...
%PY% -m venv .venv
if errorlevel 1 goto envfail
:haveenv

if exist ".venv\installed.flag" goto installed
echo Installing the required libraries. First time only, needs internet, takes 2 to 4 minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipfail
echo ok> ".venv\installed.flag"
:installed

if exist ".env" goto start
echo.
echo Paste your Gemini API key from aistudio.google.com and press Enter.
echo You can also leave it empty and paste the key in the app sidebar instead.
set "KEY="
set /p "KEY=Key: "
if not "!KEY!"=="" >".env" echo GEMINI_API_KEY=!KEY!

:start
echo.
echo Starting PrepPilot. Your browser will open at http://localhost:8501
echo Keep this window open during the demo. Close it to stop the app.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 6; Start-Process 'http://localhost:8501'"
".venv\Scripts\python.exe" -m streamlit run app.py
pause
exit /b 0

:nopython
echo.
echo Python was not found on this laptop.
echo Install Python 3.11 or newer from https://www.python.org/downloads/
echo IMPORTANT: tick "Add python.exe to PATH" on the first installer screen, then run this file again.
pause
exit /b 1

:envfail
echo Could not create the Python environment. Please send a screenshot of this window.
pause
exit /b 1

:pipfail
echo Installing libraries failed. Check your internet connection and run this file again.
pause
exit /b 1
