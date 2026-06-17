@echo off
cd /d "%~dp0"
echo Running tests...
python -m pytest tests/ -v
echo.
pause
