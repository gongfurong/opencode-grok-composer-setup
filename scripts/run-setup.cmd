@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%SCRIPT_DIR%setup-grok-composer.py" %*
  exit /b %ERRORLEVEL%
)
where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
  python3 "%SCRIPT_DIR%setup-grok-composer.py" %*
  exit /b %ERRORLEVEL%
)
echo Python 3 not found (tried python, python3)>&2
exit /b 1