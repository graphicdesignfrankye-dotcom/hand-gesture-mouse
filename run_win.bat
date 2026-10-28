@echo off
rem Avvia Hand Gesture Mouse con l'ambiente virtuale del progetto.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Esegui prima setup_win.bat
    exit /b 1
)
.venv\Scripts\python.exe hand_mouse_win.py %*
