@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
.venv\Scripts\python.exe -c "import streamlit; assert streamlit.__version__ == '1.51.0'" >nul 2>&1
if errorlevel 1 .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
start "" "http://127.0.0.1:8501"
.venv\Scripts\python.exe start.py %*
:failed
pause
