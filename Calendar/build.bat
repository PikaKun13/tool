@echo off
rem Build the portable exe -> dist\KKCalendar.exe  (runs on the .NET Framework 4.8 built into Windows 10/11)
rem Needs the .NET SDK: on PATH, or installed per-user in %LOCALAPPDATA%\Microsoft\dotnet.
rem (ASCII only on purpose: cmd.exe reads .bat in the OEM codepage.)

cd /d "%~dp0"
set "DOTNET=dotnet"
where dotnet >nul 2>nul || set "DOTNET=%LOCALAPPDATA%\Microsoft\dotnet\dotnet.exe"

"%DOTNET%" build src\KKCalendar.csproj -c Release -nologo -v q || goto :fail

rem A running copy locks dist\KKCalendar.exe: ask it to quit first.
if exist dist\KKCalendar.exe (
  dist\KKCalendar.exe --exit
  timeout /t 1 /nobreak >nul
)
if not exist dist mkdir dist
copy /y src\bin\Release\net48\KKCalendar.exe dist\ >nul || goto :fail

echo.
echo Done: dist\KKCalendar.exe
goto :eof

:fail
echo.
echo Build failed
exit /b 1
