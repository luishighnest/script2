@echo off
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "TARGET=%USERPROFILE%\Desktop\dazn1"
if not exist "%TARGET%\dazn_navigator2\__main__.py" (
    echo Cartella dazn1 non trovata in %TARGET%
    exit /b 1
)
cd /d "%TARGET%"
set "PYTHONPATH=%TARGET%"
python -m dazn_navigator2 %*
