#!/usr/bin/env python3
"""The site's icon, in one place: a dark record on the purple tile, three
grooves catching lavender light, and a purple label with a white P (chosen
2026-10-24 from a round of options, "g3"). Run it after changing a shape:

    python scripts/make_icons.py

It writes the PNGs phones use for Add to Home Screen, and puts the same
drawing, as an inline SVG, in the <link rel="icon"> of every page (the
browser tab). iOS takes only a PNG apple-touch-icon and Android's install
prompt wants 192 and 512 pixel icons, so the PNGs are drawn here, stdlib only
(zlib for the PNG), from the same shapes the SVG is written from:

    site/icon-180.png           iOS home screen (full square; iOS rounds it)
    site/icon-192.png           Android, "any" (rounded like the favicon)
    site/icon-512.png           Android, "any"
    site/icon-512-maskable.png  Android, "maskable" (full square; the
                                launcher crops it to its own shape, and the
                                record sits inside the safe circle)

The season pages get the favicon from season.template.html: run
scripts/build.py afterwards to regenerate them.
"""
import math
import re
import struct
import zlib
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

PURPLE = "#9E00C4"
INK = "#16111A"
LAVENDER = "#D7A4F0"
WHITE = "#F8F9FA"

# All in a 100 x 100 box.
TILE_RADIUS = 22
CENTRE = 50
RECORD_R = 36
# grooves that catch the light: radius, start and end angle (degrees,
# clockwise from 3 o'clock, as SVG measures them), stroke width
GROOVES = [(32, -90, 0, 2.5), (26, 90, 180, 2.5), (20, -30, 45, 2)]
LABEL_R = 13
# the P: a stem, and a bowl closed by a half circle
P_STEM = (46, 43, 49.5, 57)          # x0, y0, x1, y1
P_BOWL = (46, 43, 51.5, 51.4)
P_ROUND = (51.5, 47.2, 4.2)          # centre x, centre y, radius

SAMPLES = 4          # per side, per pixel: 16 samples smooth the edges


def _num(n):
    return ("%.2f" % n).rstrip("0").rstrip(".")


def _groove_end(r, deg):
    a = math.radians(deg)
    return CENTRE + r * math.cos(a), CENTRE + r * math.sin(a)


def svg():
    """The icon as SVG, single-quoted so it can sit in an HTML attribute."""
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>",
             f"<rect width='100' height='100' rx='{TILE_RADIUS}' fill='{PURPLE}'/>",
             f"<circle cx='{CENTRE}' cy='{CENTRE}' r='{RECORD_R}' fill='{INK}'/>"]
    for r, start, end, width in GROOVES:
        (x0, y0), (x1, y1) = _groove_end(r, start), _groove_end(r, end)
        large = 1 if end - start > 180 else 0
        parts.append(f"<path d='M{_num(x0)} {_num(y0)}A{r} {r} 0 {large} 1 {_num(x1)} {_num(y1)}' fill='none' "
                     f"stroke='{LAVENDER}' stroke-width='{_num(width)}' stroke-linecap='round'/>")
    parts.append(f"<circle cx='{CENTRE}' cy='{CENTRE}' r='{LABEL_R}' fill='{PURPLE}'/>")
    sx0, sy0, sx1, sy1 = P_STEM
    bx1, by1 = P_BOWL[2], P_BOWL[3]
    rr = P_ROUND[2]
    parts.append(f"<path d='M{_num(sx0)} {_num(sy1)}V{_num(sy0)}H{_num(bx1)}A{_num(rr)} {_num(rr)} 0 0 1 "
                 f"{_num(bx1)} {_num(by1)}H{_num(sx1)}V{_num(sy1)}Z' fill='{WHITE}'/>")
    parts.append("</svg>")
    return "".join(parts)


def favicon_href():
    return "data:image/svg+xml," + svg().replace("#", "%23")


def _rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def in_tile(x, y, radius):
    """The favicon's <rect width=100 height=100 rx=22>, in 0..100 units."""
    if not (0 <= x <= 100 and 0 <= y <= 100):
        return False
    if radius <= 0:
        return True
    cx = min(max(x, radius), 100 - radius)
    cy = min(max(y, radius), 100 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def on_groove(x, y, r, start, end, width):
    d = math.hypot(x - CENTRE, y - CENTRE)
    if abs(d - r) <= width / 2:
        a = math.degrees(math.atan2(y - CENTRE, x - CENTRE))
        if start <= a <= end:
            return True
    # round caps
    for deg in (start, end):
        ex, ey = _groove_end(r, deg)
        if math.hypot(x - ex, y - ey) <= width / 2:
            return True
    return False


def in_p(x, y):
    sx0, sy0, sx1, sy1 = P_STEM
    if sx0 <= x <= sx1 and sy0 <= y <= sy1:
        return True
    bx0, by0, bx1, by1 = P_BOWL
    if bx0 <= x <= bx1 and by0 <= y <= by1:
        return True
    cx, cy, rr = P_ROUND
    return x >= cx and (x - cx) ** 2 + (y - cy) ** 2 <= rr ** 2


def colour_at(x, y, radius):
    """What the icon shows at one point, top layer first; None outside it."""
    if not in_tile(x, y, radius):
        return None
    d = math.hypot(x - CENTRE, y - CENTRE)
    if d > RECORD_R:
        return PURPLE
    if d <= LABEL_R:
        return WHITE if in_p(x, y) else PURPLE
    for groove in GROOVES:
        if on_groove(x, y, *groove):
            return LAVENDER
    return INK


def draw(size, radius):
    colours = {c: _rgb(c) for c in (PURPLE, INK, LAVENDER, WHITE)}
    rows = []
    step = 100 / size / SAMPLES
    n = SAMPLES * SAMPLES
    for py in range(size):
        row = bytearray([0])                     # PNG filter: none
        for px in range(size):
            r = g = b = inside = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    c = colour_at((px * SAMPLES + sx + 0.5) * step, (py * SAMPLES + sy + 0.5) * step, radius)
                    if c is not None:
                        cr, cg, cb = colours[c]
                        r += cr
                        g += cg
                        b += cb
                        inside += 1
            if inside:
                row += bytes((round(r / inside), round(g / inside), round(b / inside), round(inside / n * 255)))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)     # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


ICONS = {"icon-180.png": (180, 0), "icon-192.png": (192, TILE_RADIUS), "icon-512.png": (512, TILE_RADIUS),
         "icon-512-maskable.png": (512, 0)}

# every page's favicon, except the season pages, which come from the template
FAVICON = re.compile(r'<link rel="icon" href="data:image/svg\+xml,[^"]*">')


def write_favicons():
    for page in sorted(SITE.glob("*.html")):
        if re.fullmatch(r"season\d+\.html", page.name):
            continue
        text = page.read_text(encoding="utf-8")
        new = FAVICON.sub(lambda m: f'<link rel="icon" href="{favicon_href()}">', text)
        if new != text:
            page.write_text(new, encoding="utf-8", newline="")
            print(f"favicon: site/{page.name}")


def main():
    for name, (size, radius) in ICONS.items():
        (SITE / name).write_bytes(draw(size, radius))
        print(f"wrote site/{name}")
    write_favicons()


if __name__ == "__main__":
    main()
