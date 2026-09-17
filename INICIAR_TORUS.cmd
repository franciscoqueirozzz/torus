@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_server.ps1"
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar o Torus. Consulte backend\runtime\server.err.log.
    pause
)
endlocal
