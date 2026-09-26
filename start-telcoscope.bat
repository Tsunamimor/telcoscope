@echo off
REM ============================================================
REM  telcoscope - Windows launcher
REM  Version:      v1  (Week 3, Day 2)
REM  Last updated: 2026-09-25
REM ============================================================
REM  What this does:
REM   1. Verifies (or launches) Docker Desktop and waits until
REM      the engine is responsive.
REM   2. Opens Git Bash in the project directory and runs
REM      scripts\startup.sh, which activates the conda env,
REM      brings the Docker stack up, and verifies the data
REM      layer is populated.
REM
REM  Prerequisites (adjust the paths below if yours differ):
REM   - Docker Desktop at C:\Program Files\Docker\Docker\
REM   - Git for Windows at C:\Program Files\Git\
REM   - Anaconda at C:\Users\paddy\anaconda3\
REM   - Project at   D:\Paddy\GitHub\Telcoscope\
REM
REM  Usage:
REM   Double-click this file, or run it from a terminal.
REM   The window will close automatically once Git Bash opens.
REM ============================================================

setlocal EnableDelayedExpansion

set PROJECT_DIR=D:\Paddy\GitHub\Telcoscope
set DOCKER_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe
set GIT_BASH=C:\Program Files\Git\git-bash.exe
set MAX_WAIT_SECONDS=120

echo.
echo ============================================================
echo   telcoscope launcher  (v1 - Week 3)
echo ============================================================
echo.

REM --- Sanity check: project directory exists ---
if not exist "%PROJECT_DIR%" (
    echo ERROR: Project directory not found:
    echo   %PROJECT_DIR%
    echo Edit PROJECT_DIR at the top of this script.
    pause
    exit /b 1
)

REM --- Step 1: Docker Desktop ---
echo [1/2] Checking Docker Desktop...
docker info >nul 2>&1
if !errorlevel! equ 0 (
    echo       Docker engine is already responsive.
    goto docker_ready
)

echo       Docker not responding - launching Docker Desktop...
if not exist "%DOCKER_EXE%" (
    echo ERROR: Docker Desktop not found at:
    echo   %DOCKER_EXE%
    echo Edit DOCKER_EXE at the top of this script.
    pause
    exit /b 1
)
start "" "%DOCKER_EXE%"

echo       Waiting for engine to be ready (up to %MAX_WAIT_SECONDS%s)...
set /a WAITED=0
:wait_docker
timeout /t 5 /nobreak >nul
set /a WAITED+=5
docker info >nul 2>&1
if !errorlevel! equ 0 (
    echo       Docker engine ready after !WAITED!s.
    goto docker_ready
)
if !WAITED! geq %MAX_WAIT_SECONDS% (
    echo.
    echo ERROR: Docker did not become ready within %MAX_WAIT_SECONDS%s.
    echo Check Docker Desktop manually and retry.
    pause
    exit /b 1
)
echo       ...still waiting  (!WAITED!s elapsed)
goto wait_docker

:docker_ready

REM --- Step 2: Launch Git Bash with startup script ---
echo.
echo [2/2] Opening Git Bash in the project directory...
echo.

if not exist "%GIT_BASH%" (
    echo ERROR: Git Bash not found at:
    echo   %GIT_BASH%
    echo Edit GIT_BASH at the top of this script.
    pause
    exit /b 1
)

REM --cd sets the working directory; -c runs a command, then hands over
REM to an interactive shell so the window stays open for you to work in.
start "" "%GIT_BASH%" --cd="%PROJECT_DIR%" -c "bash scripts/startup.sh; exec bash"

echo Done. This window can be closed.
echo.
timeout /t 3 /nobreak >nul
exit /b 0
