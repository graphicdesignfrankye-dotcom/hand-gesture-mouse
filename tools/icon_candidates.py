#!/usr/bin/env python3
"""Disegna le proposte di icona (1024x1024) in icons_preview/. Uso: python tools/icon_candidates.py"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2048            # si disegna al doppio e poi si riduce (bordi piu' lisci)
OUT = 1024
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "icons_preview")


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background(c1, c2, radius=0.225):
    """Quadrato arrotondato in stile macOS con sfumatura verticale e ombra."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    size = int(S * 0.805)
    x0 = (S - size) // 2
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0, x0 + 30, x0 + size, x0 + size + 30), int(size * radius), fill=(0, 0, 0, 120))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(28)))
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        gd.line((0, y, size, y), fill=lerp(c1, c2, y / size) + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), int(size * radius), fill=255)
    img.paste(grad, (x0, x0), mask)
    # leggero riflesso in alto
    shine = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shine).ellipse((-size * 0.2, -size * 0.75, size * 1.2, size * 0.45), fill=(255, 255, 255, 24))
    img.paste(shine, (x0, x0), Image.composite(shine.split()[3], Image.new("L", (size, size), 0), mask))
    return img, (x0, x0, size)


def rrect(draw, box, r, fill, grow=0):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 - grow, y0 - grow, x1 + grow, y1 + grow), r + grow, fill=fill)


def shape_layer(parts, fill, outline, width, angle=0, center=(S // 2, S // 2)):
    """Unione di rettangoli arrotondati con contorno unico; parts = [(x0, y0, x1, y1, raggio)] attorno a (0, 0)."""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    for x0, y0, x1, y1, r in parts:
        rrect(d, (cx + x0, cy + y0, cx + x1, cy + y1), r, outline, grow=width)
    for x0, y0, x1, y1, r in parts:
        rrect(d, (cx + x0, cy + y0, cx + x1, cy + y1), r, fill)
    if angle:
        layer = layer.rotate(angle, center=center, resample=Image.BICUBIC)
    return layer


def face(img, cx, cy, spread=62, size=24, brown=(70, 40, 25), cheek=(255, 130, 150), happy=True):
    d = ImageDraw.Draw(img)
    for sx in (-spread, spread):
        d.ellipse((cx + sx - size, cy - size, cx + sx + size, cy + size), fill=brown)
        d.ellipse((cx + sx - size * 0.35 + size * 0.2, cy - size * 0.7, cx + sx + size * 0.2, cy - size * 0.05), fill=(255, 255, 255))
        d.ellipse((cx + sx * 1.75 - 34, cy + 36, cx + sx * 1.75 + 34, cy + 36 + 44), fill=cheek + (170,))
    if happy:
        d.arc((cx - 58, cy + 6, cx + 58, cy + 92), 15, 165, fill=brown, width=14)


def hand_parts(finger_h=(210, 255, 238, 182), palm=(-150, -60, 150, 160)):
    px0, py0, px1, py1 = palm
    parts = [(px0, py0, px1, py1, 105)]
    xs = (-109, -37, 37, 109)
    for x, h in zip(xs, finger_h):
        parts.append((x - 33, py0 + 40 - h, x + 33, py0 + 70, 33))
    return parts


def thumb_part():
    return [(-210, -10, -145, 150, 33)]


def transparent():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def compose(colors, art, anchor, scale, dy=0):
    """Sfondo + disegno ingrandito attorno a 'anchor' e centrato nel quadrato."""
    bg, _ = background(*colors)
    box = S / scale
    ax, ay = anchor
    crop = art.crop((int(ax - box / 2), int(ay - box / 2 - dy / scale), int(ax + box / 2), int(ay + box / 2 - dy / scale)))
    bg.alpha_composite(crop.resize((S, S), Image.LANCZOS))
    return bg


# ---------------------------------------------------------------- A: la mano che saluta
def candidate_a():
    art = transparent()
    d = ImageDraw.Draw(art)
    cx, cy = S // 2, S // 2 + 40
    outline, fill = (92, 52, 22), (255, 207, 58)
    art.alpha_composite(shape_layer(thumb_part(), fill, outline, 16, angle=-14 - 38, center=(cx, cy)))
    art.alpha_composite(shape_layer(hand_parts(), fill, outline, 16, angle=-14, center=(cx, cy)))
    face_layer = transparent()
    face(face_layer, cx, cy + 20)
    art.alpha_composite(face_layer.rotate(-14, center=(cx, cy), resample=Image.BICUBIC))
    for i, r in enumerate((300, 360, 420)):
        col = (255, 255, 255, 235 - i * 45)
        d.arc((cx - r, cy - r - 40, cx + r, cy + r - 40), 296, 328, fill=col, width=26)
        d.arc((cx - r, cy - r - 40, cx + r, cy + r - 40), 212, 244, fill=col, width=26)
    return compose(((70, 130, 255), (150, 90, 255)), art, (cx, cy - 60), 1.85)


# ---------------------------------------------------------------- B: la mano e il cursore
def candidate_b():
    art = transparent()
    d = ImageDraw.Draw(art)
    cx, cy = S // 2 - 70, S // 2 + 40
    outline, fill = (60, 30, 40), (255, 138, 101)
    art.alpha_composite(shape_layer(thumb_part(), fill, outline, 16, angle=-30, center=(cx, cy)))
    art.alpha_composite(shape_layer(hand_parts(), fill, outline, 16, angle=6, center=(cx, cy)))
    face_layer = transparent()
    face(face_layer, cx, cy + 20)
    art.alpha_composite(face_layer.rotate(6, center=(cx, cy), resample=Image.BICUBIC))
    arrow = [(0, 0), (0, 300), (78, 232), (132, 360), (190, 335), (136, 208), (240, 208)]
    ax, ay = cx + 120, cy + 10
    pts = [(ax + x, ay + y) for x, y in arrow]
    d.polygon([(x + 16, y + 20) for x, y in pts], fill=(0, 0, 0, 90))
    d.polygon(pts, fill=(255, 255, 255), outline=(40, 40, 70), width=18)
    for dx, dy, r in ((-230, -250, 18), (230, -150, 14), (-60, -330, 12)):
        d.ellipse((cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r), fill=(255, 255, 255, 230))
    return compose(((0, 190, 170), (20, 110, 190)), art, (cx + 60, cy - 10), 1.9)


# ---------------------------------------------------------------- C: neon minimale
def candidate_c():
    art = transparent()
    cx, cy = S // 2, S // 2 + 60
    neon = (80, 235, 255)
    parts = hand_parts()
    mask = Image.new("L", (S, S), 0)
    inner = Image.new("L", (S, S), 0)
    md, idr = ImageDraw.Draw(mask), ImageDraw.Draw(inner)
    for x0, y0, x1, y1, r in parts:
        md.rounded_rectangle((cx + x0 - 14, cy + y0 - 14, cx + x1 + 14, cy + y1 + 14), r + 14, fill=255)
        idr.rounded_rectangle((cx + x0 + 14, cy + y0 + 14, cx + x1 - 14, cy + y1 - 14), max(r - 14, 2), fill=255)
    ring = Image.composite(Image.new("L", (S, S), 0), mask, inner)
    layer = transparent()
    layer.paste(Image.new("RGBA", (S, S), neon + (255,)), (0, 0), ring)
    halo = layer.filter(ImageFilter.GaussianBlur(26))
    art.alpha_composite(halo)
    art.alpha_composite(halo)
    art.alpha_composite(layer)
    d = ImageDraw.Draw(art)
    for x0, y0, x1, y1, r in parts[1:]:
        px, py = cx + (x0 + x1) / 2, cy + y0 + 34
        d.ellipse((px - 22, py - 22, px + 22, py + 22), fill=(255, 90, 200))
        d.ellipse((px - 9, py - 9, px + 9, py + 9), fill=(255, 255, 255))
    for px, py in ((cx - 100, cy + 40), (cx + 100, cy + 40), (cx, cy + 120)):
        d.ellipse((px - 14, py - 14, px + 14, py + 14), fill=(255, 90, 200))
    return compose(((22, 24, 48), (10, 10, 24)), art, (cx, cy - 60), 2.15)


# ---------------------------------------------------------------- D: il mignolo che risponde
def candidate_d():
    art = transparent()
    d = ImageDraw.Draw(art)
    cx, cy = S // 2 - 30, S // 2 + 120
    outline, fill = (70, 35, 60), (255, 236, 200)
    parts = [(-170, -110, 150, 170, 120), (-145, -165, -55, -70, 45), (-45, -185, 45, -70, 45), (55, -165, 145, -70, 45)]
    art.alpha_composite(shape_layer([(-215, -40, -140, 90, 36)], fill, outline, 16, angle=-20, center=(cx, cy)))
    art.alpha_composite(shape_layer([(95, -330, 165, -50, 35)], fill, outline, 16, angle=-8, center=(cx, cy)))
    art.alpha_composite(shape_layer(parts, fill, outline, 16, center=(cx, cy)))
    face(art, cx - 10, cy + 40, spread=60, size=23)
    bx, by = cx - 400, cy - 440
    d.ellipse((bx - 10, by - 6, bx + 260, by + 264), fill=(0, 0, 0, 80))
    d.ellipse((bx - 20, by - 20, bx + 240, by + 240), fill=(60, 210, 110), outline=(255, 255, 255), width=14)
    handset = [(bx + 70, by + 70), (bx + 100, by + 62), (bx + 120, by + 100), (bx + 105, by + 120), (bx + 130, by + 155),
               (bx + 150, by + 140), (bx + 188, by + 160), (bx + 180, by + 190), (bx + 150, by + 195), (bx + 80, by + 150)]
    d.polygon(handset, fill=(255, 255, 255))
    for i, r in enumerate((60, 100)):
        d.arc((bx + 300 - r, by + 40 - r, bx + 300 + r, by + 40 + r), 300, 60, fill=(255, 255, 255, 230 - i * 70), width=18)
    return compose(((255, 120, 150), (255, 170, 90)), art, (cx - 80, cy - 130), 1.8)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    names = {"A_saluta": candidate_a, "B_punta": candidate_b, "C_neon": candidate_c, "D_mignolo": candidate_d}
    thumbs = []
    for name, fn in names.items():
        img = fn().resize((OUT, OUT), Image.LANCZOS)
        img.save(os.path.join(OUT_DIR, f"icona_{name}.png"))
        thumbs.append((name, img))
    # foglio riassuntivo 2x2 con le etichette
    cell = 520
    sheet = Image.new("RGBA", (cell * 2 + 30, (cell + 50) * 2 + 10), (245, 245, 247, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
    except OSError:
        font = ImageFont.load_default()
    for i, (name, img) in enumerate(thumbs):
        x, y = 10 + (i % 2) * (cell + 10), 10 + (i // 2) * (cell + 50)
        sheet.alpha_composite(img.resize((cell, cell), Image.LANCZOS), (x, y))
        d.text((x + 8, y + cell + 6), name.replace("_", " "), fill=(30, 30, 30), font=font)
    sheet.convert("RGB").save(os.path.join(OUT_DIR, "confronto.png"))
    print("scritto in", os.path.abspath(OUT_DIR))


if __name__ == "__main__":
    main()
