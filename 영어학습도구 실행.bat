@echo off
setlocal EnableExtensions
title English Study Tool - Local AI
cd /d "%~dp0"

rem Find the program folder (the one that holds englearn\server.py).
set "ENGINE="
for /d %%D in ("%~dp0*") do if exist "%%~fD\englearn\server.py" set "ENGINE=%%~fD"
if not defined ENGINE goto noengine

set "VPY=%ENGINE%\.venv\Scripts\python.exe"
if exist "%VPY%" goto run

rem First run: create the private Python environment.
set "BASEPY="
py -3 -c "import sys" >nul 2>nul && set "BASEPY=py -3"
if not defined BASEPY python -c "import sys" >nul 2>nul && set "BASEPY=python"
if not defined BASEPY goto nopython
%BASEPY% "%ENGINE%\setup_env.py"
if errorlevel 1 goto fail
if not exist "%VPY%" goto fail

:run
"%VPY%" "%ENGINE%\app.py" %*
if errorlevel 1 goto fail
exit /b 0

:noengine
echo.
echo  [!] Program folder not found.
echo      Keep this file next to its program folder and run it again.
echo.
pause
exit /b 1

:nopython
echo.
echo  [!] Python 3.10 or newer is needed.
echo      Install it from https://www.python.org/downloads/ and run this file again.
echo.
pause
exit /b 1

:fail
echo.
echo  [!] Something went wrong. Please read the message above.
echo.
pause
exit /b 1
