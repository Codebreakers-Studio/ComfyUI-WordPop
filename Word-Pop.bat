@echo off
title Word Pop
color 0B

set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
set "PY=%APP_DIR%\venv\Scripts\python.exe"
set "PATH=%APP_DIR%\ffmpeg;%PATH%"

echo.
echo   ========================================
echo        W O R D   P O P
echo   ========================================
echo.

if not exist "%PY%" (
    echo   Run INSTALL.bat first!
    pause
    exit /b 1
)

:MENU
echo.
echo   Drop a file, or type: styles / exit
echo.
set "filepath="
set /p "filepath=  File: "
if not defined filepath goto MENU
if "%filepath%"=="exit" exit /b 0
if "%filepath%"=="styles" (
    "%PY%" "%APP_DIR%\main.py" --list-styles
    goto MENU
)
set "filepath=%filepath:"=%"
if not exist "%filepath%" (
    echo   File not found.
    goto MENU
)
echo.
echo   Style? neon clean bold minimal fire boxed  [enter = neon]
echo   Add: +karaoke +small +medium +large +top +center
echo   Example: fire +large +karaoke
echo.
set "opts="
set /p "opts=  Options: "

:: ---- Parse into separate vars ----
set "s_style=neon"
set "s_mode="
set "s_model="
set "s_pos="
set "s_words="

for %%W in (%opts%) do (
    if "%%W"=="neon"     set "s_style=neon"
    if "%%W"=="clean"    set "s_style=clean"
    if "%%W"=="bold"     set "s_style=bold"
    if "%%W"=="minimal"  set "s_style=minimal"
    if "%%W"=="fire"     set "s_style=fire"
    if "%%W"=="boxed"    set "s_style=boxed"
    if "%%W"=="+karaoke" set "s_mode=karaoke"
    if "%%W"=="+top"     set "s_pos=top"
    if "%%W"=="+center"  set "s_pos=center"
    if "%%W"=="+tiny"    set "s_model=tiny"
    if "%%W"=="+small"   set "s_model=small"
    if "%%W"=="+medium"  set "s_model=medium"
    if "%%W"=="+large"   set "s_model=large-v3"
)

:: ---- Build command ----
set "args=--style %s_style%"
if defined s_mode  set "args=%args% --mode %s_mode% --words 5"
if defined s_model set "args=%args% --model %s_model%"
if defined s_pos   set "args=%args% --position %s_pos%"

echo.
"%PY%" "%APP_DIR%\main.py" "%filepath%" %args% -y
echo.
pause
goto MENU
