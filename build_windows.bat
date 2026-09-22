@echo off
REM ---------------------------------------------------------------
REM  Builds ScrapeMaster2000.exe  (double-click this file on Windows)
REM  Needs Python 3.8+ from https://www.python.org/downloads/
REM  (tick "Add python.exe to PATH" when installing)
REM ---------------------------------------------------------------
title Building ScrapeMaster 2000
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run this again.
  pause & exit /b 1
)

echo Installing build tools...
%PY% -m pip install --upgrade --quiet pyinstaller certifi pillow || (echo pip failed & pause & exit /b 1)

echo Building...
%PY% -m PyInstaller --noconfirm --clean scrapemaster2000.spec || (echo Build failed & pause & exit /b 1)

echo.
echo Done!  Your app is here:  dist\ScrapeMaster2000.exe
echo Send that single file to anyone on Windows - they don't need Python.
explorer dist
pause
