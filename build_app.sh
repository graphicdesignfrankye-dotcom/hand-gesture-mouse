#!/bin/bash
# Crea "dist/Hand Gesture Mouse.app" con PyInstaller.
# Uso: ./build_app.sh
set -e
cd "$(dirname "$0")"

if [ ! -f .venv/bin/activate ]; then
    echo "Ambiente virtuale non trovato: crealo come descritto nel README."
    exit 1
fi

source .venv/bin/activate
pip install -q pyinstaller
rm -rf build dist
pyinstaller --noconfirm HandGestureMouse.spec

# Firma ad-hoc (necessaria su Apple Silicon) con un requisito fisso basato sull'identificativo dell'app:
# cosi' i permessi Fotocamera/Accessibilita' restano validi anche dopo aver ricompilato.
codesign --force --sign - -r='designated => identifier "com.francesco.handgesturemouse"' "dist/Hand Gesture Mouse.app"
codesign --verify --deep --strict "dist/Hand Gesture Mouse.app"

echo
echo "Fatto: dist/Hand Gesture Mouse.app"
echo "Trascinala in Applicazioni e al primo avvio concedi Fotocamera e Accessibilita'."
