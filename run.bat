@echo off
setlocal
cd /d "%~dp0"

REM Clear any prior studio server (port 8765) and worker subprocess before launching.
REM Matches by command-line so we don't kill unrelated python.exe on the machine.
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*worker.py*' -or $_.CommandLine -like '*run_studio*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul

python -m Python.scripts.studio.run_studio %*
endlocal
