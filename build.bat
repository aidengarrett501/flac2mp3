@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title FLAC2MP3 build

call :detect

if not defined PY (
    echo.
    echo No working Python installation was found.
    echo The bare "python" command on Windows 11 is a Microsoft Store stub, not Python.
    echo.
    where winget >nul 2>&1
    if errorlevel 1 (
        echo Install Python 3 from https://www.python.org/downloads/
        echo During setup, tick "Add python.exe to PATH".
        goto :fail
    )
    choice /c YN /m "Install Python now using winget"
    if errorlevel 2 goto :fail
    winget install -e --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
    echo.
    call :detect
)

if not defined PY (
    echo Python still not found. Close this window, reopen it, and run build.bat again.
    goto :fail
)

echo Using Python: %PY%
echo.
%PY% build.py
if errorlevel 1 goto :fail

echo.
pause
exit /b 0

:detect
set "PY="
for %%C in ("py -3" "python" "python3") do (
    %%~C -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=%%~C"
        exit /b
    )
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set PY="%%D\python.exe"
if defined PY exit /b
for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set PY="%%D\python.exe"
if defined PY exit /b
for /d %%D in ("%ProgramFiles(x86)%\Python3*") do if exist "%%D\python.exe" set PY="%%D\python.exe"
if defined PY exit /b
for /d %%D in ("C:\Python3*") do if exist "%%D\python.exe" set PY="%%D\python.exe"
exit /b

:fail
echo.
echo Build failed. Read the messages above.
pause
exit /b 1
