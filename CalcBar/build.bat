@echo off
rem Build the portable single-file exe -> dist\CalcBar.exe
rem Requires: pip install pyinstaller pillow
rem (ASCII only on purpose: cmd.exe reads .bat in the OEM codepage.)

cd /d "%~dp0"

python tools\make_icon.py || goto :fail

python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name CalcBar ^
  --icon assets\calcbar.ico ^
  --exclude-module numpy --exclude-module scipy --exclude-module matplotlib ^
  --exclude-module pandas --exclude-module PyQt5 --exclude-module PyQt6 ^
  --exclude-module PySide2 --exclude-module PySide6 --exclude-module IPython ^
  --exclude-module pytest --exclude-module PIL.ImageQt --exclude-module PIL.ImageTk ^
  CalcBar.pyw || goto :fail

echo.
echo Done: dist\CalcBar.exe
goto :eof

:fail
echo.
echo Build failed
exit /b 1
