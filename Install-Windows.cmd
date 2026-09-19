@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-windows.ps1"
if errorlevel 1 (
    echo.
    echo Penyiapan gagal. Lihat pesan di atas dan panduan README.md.
    pause
    exit /b 1
)
endlocal
