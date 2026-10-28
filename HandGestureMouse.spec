# -*- mode: python ; coding: utf-8 -*-
# Spec PyInstaller per creare "Hand Gesture Mouse.app". Si usa tramite build_app.sh.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("mediapipe")

a = Analysis(
    ["hand_mouse.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],   # hand_mouse.py lo sostituisce con un modulo vuoto
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HandGestureMouse",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="HandGestureMouse")
app = BUNDLE(
    coll,
    name="Hand Gesture Mouse.app",
    bundle_identifier="com.francesco.handgesturemouse",
    icon="icons/AppIcon.icns",
    info_plist={
        "CFBundleName": "Hand Gesture Mouse",
        "CFBundleDisplayName": "Hand Gesture Mouse",
        "CFBundleShortVersionString": "1.0.0",
        "NSCameraUsageDescription": "Hand Gesture Mouse usa la webcam per riconoscere i gesti della mano e muovere il cursore.",
        "NSHighResolutionCapable": True,
    },
)
