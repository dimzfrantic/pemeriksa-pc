@echo off
REM ============================================================
REM  PC Monitor Agent - Installer EXE (Kemenkum Jabar)
REM  Untuk dijalankan di tiap PC. TIDAK perlu Python.
REM  Agen auto-start sendiri via registry Run saat dijalankan.
REM ============================================================
setlocal

set "AGENTDIR=%~dp0"
set "AGENTDIR=%AGENTDIR:~0,-1%"

echo.
echo === Installer PC Monitor Agent (EXE) - Kemenkum Jabar ===
echo Folder: %AGENTDIR%
echo.

REM 1. Cek exe
if not exist "%AGENTDIR%\pcmonitor-agent.exe" (
  echo [PENTING] pcmonitor-agent.exe tidak ditemukan di folder ini.
  echo Build dulu di satu PC ber-Python dengan build.bat, lalu salin exe-nya ke sini.
  pause
  exit /b 1
)

REM 2. Cek .env
if not exist "%AGENTDIR%\.env" (
  if exist "%AGENTDIR%\.env.example" (
    copy /Y "%AGENTDIR%\.env.example" "%AGENTDIR%\.env" >nul
    echo [info] .env dibuat dari .env.example
  )
  echo.
  echo [PENTING] Buka file .env, ubah AGENT_NAME sesuai nama PC ini
  echo ^(mis. "Pc Aula"^), lalu jalankan installer ini lagi.
  notepad "%AGENTDIR%\.env"
  pause
  exit /b 1
)

REM 3. Uji lapor sekali (exe juga memasang registry Run otomatis)
echo === Menjalankan agen (uji lapor + pasang auto-start) ===
"%AGENTDIR%\pcmonitor-agent.exe" once

REM 4. Jalankan agen di latar belakang (mulai heartbeat sekarang)
start "" "%AGENTDIR%\pcmonitor-agent.exe"

echo.
echo === SELESAI ===
echo Agen berjalan dan akan otomatis aktif tiap login Windows.
echo Cek di server: ketik "status pc <nama>" di topik Telegram Pemeriksaan PC.
echo.
pause
endlocal
