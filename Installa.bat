@echo off
color 0B
echo ==============================================================
echo       INSTALLAZIONE COMPONENTI DAZN PROVA (IBRIDO)
echo ==============================================================
echo.

:: Controllo Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRORE] Python non trovato! Installa Python 3.10+ da python.org
    echo          e spunta Add Python to PATH durante l'installazione.
    pause
    exit /b
)
echo [OK] Python trovato:
python --version
echo.

echo [1/4] Installazione librerie Python (curl_cffi, playwright, pywidevine, etc.)...
pip install -e "%~dp0."
if %errorlevel% neq 0 (
    echo [ERRORE] Installazione pip fallita.
    pause
    exit /b
)
echo.

echo [2/4] Installazione browser headless per login ed estrazione...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [ERRORE] Installazione Chromium fallita.
    pause
    exit /b
)
echo.

echo [3/4] Registrazione comando globale 'mpd'...
for /f "delims=" %%I in ('python -c "import sys, pathlib; print(pathlib.Path(sys.executable).parent / 'Scripts')"') do set "SCRIPTS_DIR=%%I"
if exist "%SCRIPTS_DIR%" (
    if exist "%SCRIPTS_DIR%\mpd.exe" del /f /q "%SCRIPTS_DIR%\mpd.exe" >nul 2>&1
    if exist "%SCRIPTS_DIR%\mpd.cmd" del /f /q "%SCRIPTS_DIR%\mpd.cmd" >nul 2>&1
    (
        echo @echo off
        echo set "FOUND="
        echo if exist "%%CD%%\dazn_navigator2\__main__.py" (
        echo     cd /d "%%CD%%"
        echo     python -m dazn_navigator2 %%*
        echo     exit /b 0
        echo )
        echo for /d %%%%D in ("%%USERPROFILE%%\Desktop\dazn*" "%%USERPROFILE%%\Desktop\DAZN*") do (
        echo     if exist "%%%%~fD\dazn_navigator2\__main__.py" set "FOUND=%%%%~fD"
        echo )
        echo if defined FOUND (
        echo     cd /d "%%FOUND%%"
        echo     python -m dazn_navigator2 %%*
        echo     exit /b 0
        echo )
        echo python -m dazn_navigator2 %%*
        echo exit /b 0
    ) > "%SCRIPTS_DIR%\mpd.bat"
    echo [OK] Comando 'mpd' registrato in %SCRIPTS_DIR%\mpd.bat
)
echo.

echo [4/4] Verifica file Widevine device.wvd...
if exist "%~dp0device.wvd" (
    echo [OK] device.wvd presente nella cartella.
) else (
    echo [ATTENZIONE] device.wvd NON trovato! L'estrazione eventi non funzionera'.
    echo              Copia un file .wvd in questa cartella col nome device.wvd
)
echo.

echo ==============================================================
echo   INSTALLAZIONE COMPLETATA!
echo   Puoi avviare il programma in 2 modi:
echo   1. Cliccando su Avvia.bat
echo   2. Digitando 'mpd' da qualsiasi terminale
echo ==============================================================
pause

