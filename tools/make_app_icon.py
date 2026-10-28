#!/usr/bin/env python3
"""Crea le icone dell'app dalla proposta A (la mano che saluta): icons/AppIcon.png, .icns (Mac) e .ico (Windows).

Uso: python tools/make_app_icon.py     (serve macOS per iconutil; l'.ico si crea ovunque)
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402

import icon_candidates as ic  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "icons")


def main():
    os.makedirs(OUT, exist_ok=True)
    master = ic.candidate_a().resize((1024, 1024), Image.LANCZOS)
    master.save(os.path.join(OUT, "AppIcon.png"))
    master.save(os.path.join(OUT, "AppIcon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if shutil.which("iconutil"):
        iconset = os.path.join(OUT, "AppIcon.iconset")
        shutil.rmtree(iconset, ignore_errors=True)
        os.makedirs(iconset)
        for size in (16, 32, 128, 256, 512):
            master.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, f"icon_{size}x{size}.png"))
            master.resize((size * 2, size * 2), Image.LANCZOS).save(os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(OUT, "AppIcon.icns")], check=True)
        shutil.rmtree(iconset)
    print("icone in", os.path.abspath(OUT), os.listdir(OUT))


if __name__ == "__main__":
    main()
