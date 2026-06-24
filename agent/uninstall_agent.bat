@echo off
REM Hapus PC Monitor Agent: matikan proses + hapus registry Run
setlocal
echo Menghentikan agen ...
taskkill /IM pcmonitor-agent.exe /F >nul 2>&1

REM Hapus semua entri Run yang diawali PCMonitorAgent_
for /f "tokens=1,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" 2^>nul ^| findstr /I "PCMonitorAgent_"') do (
  reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%%A" /f >nul 2>&1
  echo Hapus auto-start: %%A
)
echo Selesai. Agen dihentikan dan auto-start dihapus.
pause
endlocal
