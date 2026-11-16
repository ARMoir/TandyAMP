@ECHO OFF
CD /D "%~dp0"
PY -3.11 studio.py %*
IF ERRORLEVEL 1 (
 ECHO.
 ECHO Studio failed. Check Python 3.11 and install the dependencies.
 PAUSE
)
