@echo off
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
title Script2

cd /d "%~dp0"

set PY=C:\Users\alecl\AppData\Local\Programs\Python\Python313\python.exe
set CF=C:\Users\alecl\AppData\Local\Temp\opencode\cloudflared.exe
set CFLOG=%TEMP%\opencode\cf_bat.log
if exist "%CFLOG%" del "%CFLOG%" >nul 2>&1

echo ==============================================
echo   AVVIO Script2
echo ==============================================
echo.

echo [1/4] Avvio il server Flask su localhost:5000...
if not exist "%PY%" (
    echo [ERRORE] Python non trovato: %PY%
    pause
    exit /b 1
)
start "Script2 - Flask" /min "%PY%" app.py

echo [2/4] Avvio il tunnel Cloudflare (trycloudflare.com)...
if not exist "%CF%" (
    echo [ERRORE] cloudflared.exe non trovato: %CF%
    pause
    exit /b 1
)
start "Script2 - Tunnel" /min "%CF%" tunnel --url http://localhost:5000 --no-autoupdate --logfile "%CFLOG%" --loglevel info

echo [3/4] Attendo l'avvio del tunnel...
timeout /t 12 /nobreak >nul

echo [4/4] Estraggo il link pubblico e aggiorno il redirect GitHub Pages...
set "PUBLIC="
for /f "tokens=*" %%L in ('findstr /C:"trycloudflare.com" "%CFLOG%"') do (
    for /f "tokens=3" %%U in ("%%L") do set "PUBLIC=%%U"
)
if defined PUBLIC (
    set PUBLIC=%PUBLIC:^|=%
    echo   Link pubblico: %PUBLIC%
    echo   Aggiorno https://luishighnest.github.io/script2/ ...
    "%PY%" update_redirect.py "%PUBLIC%"
    echo.
    echo ==============================================
    echo   SITO ONLINE
    echo   Da condividere (link fisso): https://luishighnest.github.io/script2/
    echo   Link pubblico attuale:        %PUBLIC%
    echo   Link locale:                  http://localhost:5000
    echo ==============================================
) else (
    echo   Il link non e' ancora pronto.
    echo   Guarda tra poco nella finestra "Script2 - Tunnel", poi lancia:
    echo   "%PY%" update_redirect.py IL-LINK
)
echo.

start http://localhost:5000
pause