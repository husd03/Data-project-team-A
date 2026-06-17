@echo off
cd /d "%~dp0"
echo Installing requirements...
python -m pip install -r requirements.txt
echo.
echo Done! You can now run spustit_agenta.bat
pause
