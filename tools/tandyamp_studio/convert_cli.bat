@ECHO OFF
CD /D "%~dp0"
PY -3.11 studio.py --cli %*
EXIT /B %ERRORLEVEL%
