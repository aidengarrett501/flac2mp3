"""Packs the build sources into one self-extracting FLAC2MP3-build.bat.

Run this whenever you change flac2mp3_gui.py, build.py, installer.iss or the
icon, then hand out (or keep) the single .bat.
"""

import base64
import io
import textwrap
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "FLAC2MP3-build.bat"
MARKER = "#PAYLOAD_BEGIN#"

PAYLOAD_FILES = [
    "flac2mp3_gui.py",
    "build.py",
    "installer.iss",
    "flac2mp3.ico",
]

STUB = r"""@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title FLAC2MP3 build

echo Building FLAC2MP3. This installs anything it needs along the way.
echo.

call :detect

if not defined PY (
    echo No working Python installation was found.
    echo The bare "python" command on Windows 11 is a Store stub, not Python.
    echo.
    where winget >nul 2>&1
    if errorlevel 1 (
        echo Install Python 3 from https://www.python.org/downloads/
        echo During setup, tick "Add python.exe to PATH".
        goto :fail
    )
    echo Installing Python with winget. Approve the UAC prompt if one appears.
    winget install -e --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
    echo.
    call :detect
)

if not defined PY (
    echo Python still not found. Close this window, reopen it, and run again.
    goto :fail
)

echo Using Python: %PY%

set "WORK=%TEMP%\flac2mp3-build"
if exist "%WORK%" rd /s /q "%WORK%"
mkdir "%WORK%" 2>nul

echo Unpacking build sources...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$t=[IO.File]::ReadAllText('%~f0'); $b=($t -split '#PAYLOAD_BEGIN#')[-1] -replace '\s',''; [IO.File]::WriteAllBytes('%WORK%\payload.zip',[Convert]::FromBase64String($b)); Expand-Archive -LiteralPath '%WORK%\payload.zip' -DestinationPath '%WORK%' -Force"
if errorlevel 1 goto :fail
if not exist "%WORK%\build.py" (
    echo Could not unpack the build sources.
    goto :fail
)

set "FLAC2MP3_HOME=%~dp0"
pushd "%WORK%"
%PY% build.py
set "RC=!errorlevel!"
popd

rd /s /q "%WORK%" 2>nul
if not "%RC%"=="0" goto :fail

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

"""


def main():
    missing = [n for n in PAYLOAD_FILES if not (HERE / n).is_file()]
    if missing:
        print("Missing source files: " + ", ".join(missing))
        return 1

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in PAYLOAD_FILES:
            zf.write(HERE / name, arcname=name)

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    wrapped = "\n".join(textwrap.wrap(encoded, 76))

    text = STUB.replace("\n", "\r\n") + MARKER + "\r\n" + wrapped.replace("\n", "\r\n") + "\r\n"
    OUT.write_bytes(text.encode("ascii"))

    print(f"Wrote {OUT.name}  ({OUT.stat().st_size // 1024} KB)")
    print("Payload: " + ", ".join(PAYLOAD_FILES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
