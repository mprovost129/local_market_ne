@echo off
setlocal enabledelayedexpansion

set CMD=python manage.py launch_gate --json
if "%FAIL_ON_WARNING%"=="1" (
  set CMD=!CMD! --fail-on-warning
)

%CMD%
exit /b %ERRORLEVEL%
