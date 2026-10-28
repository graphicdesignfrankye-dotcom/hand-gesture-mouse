@echo off
rem Crea l'ambiente virtuale e installa le librerie (una volta sola). Serve Python 3.9-3.12 da python.org.
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Python non trovato. Installa Python 3.11 da https://www.python.org/downloads/ spuntando "Add python.exe to PATH".
    exit /b 1
)
if not exist .venv\Scripts\python.exe (
    py -3.11 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || py -3.10 -m venv .venv 2>nul || py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-windows.txt
echo.
echo Fatto. Avvia con run_win.bat
