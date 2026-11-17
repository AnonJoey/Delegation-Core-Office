@echo off
rem delegation-core installer for Windows.
rem
rem Only finds a Python 3.11+ and hands over to install.py, which does the rest
rem (venv, backup, pip, post-install) the same way on every platform. Before
rem 2026-10-06 that logic lived here and again in install.sh, and the two
rem copies had drifted apart.
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "SCRIPT_DIR=%~dp0"
set "PYTHON="

where py >nul 2>&1
if not errorlevel 1 (
    for %%v in (3.13 3.12 3.11) do (
        if not defined PYTHON (
            py -%%v -c "import sys; assert sys.version_info>=(3,11)" >nul 2>&1
            if not errorlevel 1 set "PYTHON=py -%%v"
        )
    )
)
if not defined PYTHON (
    for %%c in (python python3) do (
        if not defined PYTHON (
            %%c -c "import sys; assert sys.version_info>=(3,11)" >nul 2>&1
            if not errorlevel 1 set "PYTHON=%%c"
        )
    )
)
if not defined PYTHON (
    echo.
    echo  ERROR: Python 3.11+ is required.
    echo  Make sure to check "Add Python to PATH" during installation.
    echo  After installing Python, run this installer again.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

!PYTHON! "%SCRIPT_DIR%install.py" %*
set "CODE=%ERRORLEVEL%"
echo.
pause
exit /b %CODE%
