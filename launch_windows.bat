@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt || goto :error
py -3 app.py || goto :error
exit /b 0
:error
pause
exit /b 1
