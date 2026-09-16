@echo off
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
for %%I in ("%~dp0.") do title %%~nxI
python -m dazn_navigator2 %*
exit /b 0
