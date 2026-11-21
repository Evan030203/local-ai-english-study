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
rem Python 3.10 - 3.14 only: some speech parts have no build for newer versions yet.
echo.
echo  First run: looking for Python 3.10 - 3.14 ...
set "BASEPY="
set "HASPM="
where pymanager >nul 2>nul
if errorlevel 1 goto findpy
set "HASPM=1"
echo  Python install manager found. Making sure Python 3.14 is installed ...
pymanager install 3.14
echo.
:findpy
call :trypy 3.14
if defined HASPM if not defined BASEPY call :trycmd pymanager exec -V:3.14
call :trypy 3.13
call :trypy 3.12
call :trypy 3.11
call :trypy 3.10
if not defined BASEPY call :trycmd py -3
if not defined BASEPY call :trycmd python
if not defined BASEPY goto nopython
echo  Using: %BASEPY%
%BASEPY% "%ENGINE%\setup_env.py"
if errorlevel 1 goto fail
if not exist "%VPY%" goto fail

:run
"%VPY%" "%ENGINE%\app.py" %*
if errorlevel 1 goto fail
exit /b 0

:trypy
if defined BASEPY exit /b 0
py -%1 -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 0
set "BASEPY=py -%1"
exit /b 0

:trycmd
if defined BASEPY exit /b 0
%* -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 0
set "BASEPY=%*"
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
echo  [!] Python 3.10 - 3.14 is needed.
echo      Install "Python Install Manager" from the Microsoft Store
echo      (or Python 3.14 from https://www.python.org/downloads/)
echo      and run this file again.
echo.
pause
exit /b 1

:fail
echo.
echo  [!] Something went wrong. Please read the message above.
echo.
pause
exit /b 1
