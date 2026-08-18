@echo off
setlocal EnableExtensions
set "SCRIPT=%~1"
if "%SCRIPT%"=="" exit /b 1
set "GITCOMMON="
for /f "delims=" %%I in ('git rev-parse --path-format=absolute --git-common-dir 2^>nul') do set "GITCOMMON=%%I"
if not defined GITCOMMON (
  for /f "delims=" %%I in ('git rev-parse --git-common-dir 2^>nul') do set "GITCOMMON=%%I"
)
if not defined GITCOMMON exit /b 1
for %%I in ("%GITCOMMON%\..") do set "ROOT=%%~fI"
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" exit /b 1
if exist "%CD%\%SCRIPT%" (
  set "SCRIPT=%CD%\%SCRIPT%"
) else if exist "%ROOT%\%SCRIPT%" (
  set "SCRIPT=%ROOT%\%SCRIPT%"
)
if not exist "%SCRIPT%" exit /b 1
"%PY%" "%SCRIPT%"
