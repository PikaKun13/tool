@echo off
rem Run from source (needs Python 3.10+ installed). No console window.
rem (ASCII only on purpose: cmd.exe reads .bat in the OEM codepage.)
cd /d "%~dp0"
start "" pythonw CalcBar.pyw
