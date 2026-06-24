@echo off
REM ============================================================
REM  Build PC Monitor Agent jadi .exe (PyInstaller)
REM  Jalankan SEKALI di SATU PC Windows yang ada Python 3.
REM  Hasil: dist\pcmonitor-agent.exe  (sebar ke PC lain tanpa Python)
REM ============================================================
setlocal

if not exist venv (
  python -m venv venv
)

call venv\Scripts\activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller --noconsole --onefile --name "pcmonitor-agent" agent.py

if exist .env.example copy /Y .env.example dist\.env.example >nul

echo.
echo === Build selesai ===
echo File: dist\pcmonitor-agent.exe
echo Salin pcmonitor-agent.exe + .env (dari .env.example) ke tiap PC.
echo.
pause
endlocal
