@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python.exe -c "import fastapi, uvicorn, jsonschema, openpyxl, dotenv" 2>nul || .venv\Scripts\python.exe -m pip install -r requirements-matching.txt
if errorlevel 1 goto end
.venv\Scripts\python.exe -m src.start_integrated
:end
pause
