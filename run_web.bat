@echo off
cd /d "%~dp0"
.\.venv\Scripts\pip.exe install -r server\requirements.txt
echo.
echo Open: http://127.0.0.1:8000
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8000
