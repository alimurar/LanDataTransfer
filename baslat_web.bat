@echo off
title LAN Transfer - Web Sunucusu
cd /d "%~dp0"
echo ===================================================
echo     LAN Transfer Web Sunucusu Baslatiliyor...
echo ===================================================

where python >nul 2>&1
if %errorlevel% equ 0 (
    python lan_web.py
    goto end
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py lan_web.py
    goto end
)

echo.
echo [HATA] Bilgisayarda Python bulunamadi!
pause

:end
if errorlevel 1 pause
