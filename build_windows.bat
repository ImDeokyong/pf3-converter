@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt pyinstaller || goto :error
py -3 -m PyInstaller --noconfirm --clean --windowed --onefile --name PF3Converter --version-file version_info.txt --hidden-import tkinter --collect-all rawpy app.py || goto :error
echo Build succeeded: dist\PF3Converter.exe
pause
exit /b 0
:error
pause
exit /b 1
