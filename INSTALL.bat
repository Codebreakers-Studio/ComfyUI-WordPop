@echo off
title Word Pop - Setup
color 0B

set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

echo.
echo   ========================================
echo     W O R D   P O P   -   S E T U P
echo   ========================================
echo.
echo   [1/3] Checking Python...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0E
    echo   Python not found. Opening download page...
    echo   IMPORTANT: Check "Add Python to PATH" during install!
    start "" "https://www.python.org/downloads/"
    echo.
    echo   After installing, run INSTALL.bat again.
    goto :FAIL
)
python --version

echo.
echo   [2/3] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Not found - downloading FFmpeg...
    mkdir "%APP_DIR%\ffmpeg" 2>nul
    curl -L "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -o "%APP_DIR%\ffmpeg\ffmpeg.zip"
    if not exist "%APP_DIR%\ffmpeg\ffmpeg.zip" (
        echo   [ERROR] Download failed.
        echo   Install manually: https://www.gyan.dev/ffmpeg/builds/
        goto :FAIL
    )
    echo   Extracting...
    powershell -Command "Expand-Archive -Path '%APP_DIR%\ffmpeg\ffmpeg.zip' -DestinationPath '%APP_DIR%\ffmpeg' -Force"
    for /d %%D in ("%APP_DIR%\ffmpeg\ffmpeg-*") do (
        copy "%%D\bin\ffmpeg.exe" "%APP_DIR%\ffmpeg\" >nul 2>&1
        copy "%%D\bin\ffprobe.exe" "%APP_DIR%\ffmpeg\" >nul 2>&1
    )
    if not exist "%APP_DIR%\ffmpeg\ffmpeg.exe" (
        echo   [ERROR] Extraction failed.
        echo   Install manually: https://www.gyan.dev/ffmpeg/builds/
        goto :FAIL
    )
    del "%APP_DIR%\ffmpeg\ffmpeg.zip" 2>nul
    for /d %%D in ("%APP_DIR%\ffmpeg\ffmpeg-*") do rd /s /q "%%D" 2>nul
    echo   FFmpeg installed.
) else (
    echo   FFmpeg found.
)

echo.
echo   [3/3] Installing Word Pop packages...
if not exist "%APP_DIR%\venv\Scripts\python.exe" (
    echo   Creating environment...
    python -m venv "%APP_DIR%\venv"
)
if not exist "%APP_DIR%\venv\Scripts\python.exe" (
    echo   [ERROR] Venv creation failed.
    goto :FAIL
)
"%APP_DIR%\venv\Scripts\pip.exe" install -r "%APP_DIR%\requirements.txt"
if not exist "%APP_DIR%\venv\Scripts\python.exe" (
    echo   [ERROR] Install failed.
    goto :FAIL
)

echo.
color 0A
echo   ========================================
echo     SETUP COMPLETE
echo   ========================================
echo.
echo   Double-click Word-Pop.bat to start.
echo.
pause
exit /b 0

:FAIL
echo.
color 0C
echo   Setup did not complete. See error above.
echo.
pause
exit /b 1
