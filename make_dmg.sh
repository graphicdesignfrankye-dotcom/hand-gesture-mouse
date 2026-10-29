#!/usr/bin/env bash
# Crea dist/Hand-Gesture-Mouse-macOS.dmg: finestra con sfondo, l'app e la scorciatoia ad Applicazioni.
# Prima serve l'app compilata (./build_app.sh). Installa da solo dmgbuild e Pillow nell'ambiente attivo.
set -euo pipefail
cd "$(dirname "$0")"
APP="dist/Hand Gesture Mouse.app"
[ -d "$APP" ] || { echo "Manca $APP: esegui prima ./build_app.sh"; exit 1; }
[ -f .venv/bin/activate ] && source .venv/bin/activate
python -m pip install --quiet dmgbuild pillow

rm -rf dist/dmg-bg dist/Hand-Gesture-Mouse-macOS.dmg
python tools/make_dmg_background.py dist/dmg-bg
tiffutil -cathidpicheck dist/dmg-bg/background.png dist/dmg-bg/background@2x.png -out dist/dmg-bg/background.tiff
dmgbuild -s tools/dmg_settings.py -D app="$APP" -D bg=dist/dmg-bg/background.tiff \
  "Hand Gesture Mouse" dist/Hand-Gesture-Mouse-macOS.dmg > /dev/null
rm -rf dist/dmg-bg
ls -lh dist/Hand-Gesture-Mouse-macOS.dmg
