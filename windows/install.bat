@echo off
REM BoxedLANG Windows installer launcher.
REM Double-click this file to install BoxedLANG (CLI tools + IDE).
REM No admin rights needed - installs for the current user only.

setlocal
set SCRIPT_DIR=%~dp0

echo Starting BoxedLANG installer...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" %*

echo.
pause
