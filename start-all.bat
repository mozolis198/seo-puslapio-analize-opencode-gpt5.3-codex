@echo off
setlocal

set ROOT=%~dp0

start "Backend API" cmd /k "cd /d ""%ROOT%backend"" && if not exist .venv (python -m venv .venv && .\.venv\Scripts\python.exe -m pip install -r requirements.txt) && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

start "Frontend Web" cmd /k "cd /d ""%ROOT%web"" && if not exist node_modules (npm install) && npm run dev -- -p 3001"

echo Started backend (8000) and frontend (3001).
echo Open http://localhost:3001

endlocal
