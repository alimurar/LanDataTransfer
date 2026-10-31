@echo off
title LAN Transfer - Guvenlik Duvari ve Ag Yapilandirmasi
cd /d "%~dp0"

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo ===================================================
    echo   [DIKKAT] Bu dosya Yonetici Yetkisi Gerektirir!
    echo ===================================================
    echo.
    echo Lutfen bu dosyaya SAG TIKLAYIP:
    echo "Yonetici olarak calistir" secenegine tiklayin.
    echo.
    pause
    exit /b
)

echo ===================================================
echo   LAN Transfer Icin Ag ve Guvenlik Duvari Ayarlaniyor
echo ===================================================
echo.

echo 1. Bagli aglar Ozel Ag (Private Network) yapiliyor...
powershell -Command "Set-NetConnectionProfile -InterfaceAlias 'Ethernet' -NetworkCategory Private"
powershell -Command "Set-NetConnectionProfile -InterfaceAlias 'Ethernet 4' -NetworkCategory Private"
powershell -Command "Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private"

echo 2. Windows Guvenlik Duvarinda portlara izin veriliyor...
netsh advfirewall firewall delete rule name="LAN Transfer Web" >nul 2>&1
netsh advfirewall firewall add rule name="LAN Transfer Web" dir=in action=allow protocol=TCP localport=8990-8999 profile=any
netsh advfirewall firewall delete rule name="LAN Transfer GUI TCP" >nul 2>&1
netsh advfirewall firewall add rule name="LAN Transfer GUI TCP" dir=in action=allow protocol=TCP localport=39000-39010 profile=any
netsh advfirewall firewall delete rule name="LAN Transfer GUI UDP" >nul 2>&1
netsh advfirewall firewall add rule name="LAN Transfer GUI UDP" dir=in action=allow protocol=UDP localport=39005 profile=any

echo.
echo ===================================================
echo [BASARILI] Tum izinler verildi ve Ozel Ag yapildi!
echo ===================================================
echo.
pause
