#!/bin/bash
# Avvia Hand Gesture Mouse usando il venv del progetto.
# Uso: ./run.sh
set -e
cd "$(dirname "$0")"

if [ ! -f .venv/bin/activate ]; then
    echo "Ambiente virtuale non trovato. Crealo con:"
    echo "  python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
    exit 1
fi

source .venv/bin/activate
exec python hand_mouse.py "$@"
