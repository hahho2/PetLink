@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo PetLink's local Python environment was not found.
    echo Create it first with: python -m venv .venv
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0src"
set "PETLINK_PYTHON=.venv\Scripts\python.exe"

"%PETLINK_PYTHON%" -c "import PySide6, sqlalchemy, alembic" >nul 2>&1
if errorlevel 1 set "PETLINK_PYTHON=python"

"%PETLINK_PYTHON%" -m petlink

if errorlevel 1 (
    echo.
    echo PetLink could not start. Check that its project dependencies are installed in .venv.
    pause
)
endlocal
