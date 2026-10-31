@echo off
title LAN Transfer - Masaustu Arayuzu
cd /d "%~dp0"
echo ===================================================
echo     LAN Transfer Masaustu Uygulamasi Baslatiliyor...
echo ===================================================

where python >nul 2>&1
if %errorlevel% equ 0 (
    python lan_transfer_gui.py
    goto end
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py lan_transfer_gui.py
    goto end
)

echo.
echo [HATA] Bilgisayarda Python bulunamadi!
pause

:end
if errorlevel 1 pause
