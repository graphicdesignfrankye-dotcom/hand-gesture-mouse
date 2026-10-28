@echo off
rem Crea "dist\Hand Gesture Mouse\Hand Gesture Mouse.exe" (da eseguire su Windows, dopo setup_win.bat).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Esegui prima setup_win.bat
    exit /b 1
)
call .venv\Scripts\activate.bat
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Hand Gesture Mouse" --icon icons\AppIcon.ico ^
  --collect-all mediapipe --collect-all pygrabber ^
  --exclude-module matplotlib ^
  --hidden-import pystray._win32 --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  hand_mouse_win.py
echo.
echo Fatto: dist\Hand Gesture Mouse\Hand Gesture Mouse.exe
echo Il log degli errori e' in %%LOCALAPPDATA%%\Hand Gesture Mouse\log.txt
