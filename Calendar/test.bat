@echo off
rem Run the unit tests (holiday rules vs. the Cabinet Office CSV, kyureki table, ...).
rem (ASCII only on purpose: cmd.exe reads .bat in the OEM codepage.)
cd /d "%~dp0"
set "DOTNET=dotnet"
where dotnet >nul 2>nul || set "DOTNET=%LOCALAPPDATA%\Microsoft\dotnet\dotnet.exe"
"%DOTNET%" test tests\KKCalendar.Tests.csproj -nologo
