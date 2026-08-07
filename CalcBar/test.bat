@echo off
rem Run all tests. The UI test briefly flashes a window on screen; that is normal.
rem (ASCII only on purpose: cmd.exe reads .bat in the OEM codepage.)
cd /d "%~dp0"
python -m unittest discover -s tests -t . -v
