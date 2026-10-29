#!/usr/bin/env python3
"""Disegna lo sfondo del DMG (660x400, piu' la versione Retina) con la freccia «trascina in Applicazioni».

Uso: python tools/make_dmg_background.py CARTELLA_DI_USCITA   ->  background.png e background@2x.png
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 660, 400


def font(size):
    for path in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf",
                 "/Library/Fonts/Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(scale):
    w, h = W * scale, H * scale
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    c1, c2 = (238, 242, 255), (226, 218, 255)          # lavanda chiaro, come l'icona
    for y in range(h):
        t = y / h
        d.line((0, y, w, y), fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    violet = (122, 92, 255)
    # freccia a tre chevron tra l'app (x=170) e Applications (x=490), all'altezza delle icone (y=200)
    cy = 200 * scale
    for i, x in enumerate((262, 318, 374)):
        x *= scale
        a = 22 * scale
        shade = tuple(int(violet[k] + (255 - violet[k]) * (0.55 - i * 0.22)) for k in range(3))
        d.line((x, cy - a, x + a, cy), fill=shade, width=9 * scale, joint="curve")
        d.line((x + a, cy, x, cy + a), fill=shade, width=9 * scale, joint="curve")
        for ex, ey in ((x, cy - a), (x, cy + a), (x + a, cy)):
            r = 4.5 * scale
            d.ellipse((ex - r, ey - r, ex + r, ey + r), fill=shade)
    text = "Trascina Hand Gesture Mouse nella cartella Applicazioni"
    f = font(15 * scale)
    tw = d.textlength(text, font=f)
    d.text(((w - tw) / 2, 330 * scale), text, fill=(70, 60, 120), font=f)
    f2 = font(12 * scale)
    sub = "Al primo avvio: click destro sull'app > Apri, poi consenti Fotocamera e Accessibilità"
    tw2 = d.textlength(sub, font=f2)
    d.text(((w - tw2) / 2, 358 * scale), sub, fill=(120, 110, 160), font=f2)
    return img


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    draw(1).save(os.path.join(out, "background.png"), dpi=(72, 72))
    draw(2).save(os.path.join(out, "background@2x.png"), dpi=(144, 144))
    print("sfondi in", out)


if __name__ == "__main__":
    main()
