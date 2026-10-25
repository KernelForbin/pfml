#!/usr/bin/env python3
"""Draw the site's app icons as PNGs, for Add to Home Screen.

    python scripts/make_icons.py

The favicon is an inline SVG (a purple rounded square with a white "P",
in every page's <head>), but phones want PNGs: iOS takes only a PNG
apple-touch-icon, and Android's install prompt wants 192 and 512 pixel
icons in the manifest. This draws the same shape at those sizes, stdlib
only (zlib for the PNG), so the icons can be rebuilt without an image
library and always match the favicon:

    site/icon-180.png           iOS home screen (full square; iOS rounds it)
    site/icon-192.png           Android, "any" (rounded like the favicon)
    site/icon-512.png           Android, "any"
    site/icon-512-maskable.png  Android, "maskable" (full square; the
                                launcher crops it to its own shape, and
                                the P sits inside the safe circle)
"""
import struct
import zlib
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PURPLE = (0x9E, 0x00, 0xC4)
WHITE = (0xF8, 0xF9, 0xFA)
SAMPLES = 4          # per side, per pixel: 16 samples smooth the edges


def in_rounded_square(x, y, radius):
    """The favicon's <rect width=100 height=100 rx=22>, in 0..100 units."""
    if radius <= 0:
        return 0 <= x <= 100 and 0 <= y <= 100
    cx = min(max(x, radius), 100 - radius)
    cy = min(max(y, radius), 100 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def in_p(x, y):
    """The favicon's path M30 74V26h22a14 14 0 010 28H44v20z: a stem,
    a bar across the top, and a half-disc closing the bowl."""
    if 30 <= x <= 44 and 26 <= y <= 74:
        return True
    if 30 <= x <= 52 and 26 <= y <= 54:
        return True
    return x >= 52 and (x - 52) ** 2 + (y - 40) ** 2 <= 14 ** 2


def draw(size, radius):
    rows = []
    step = 100 / size / SAMPLES
    for py in range(size):
        row = bytearray([0])                     # PNG filter: none
        for px in range(size):
            back = mark = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px * SAMPLES + sx + 0.5) * step
                    y = (py * SAMPLES + sy + 0.5) * step
                    if in_rounded_square(x, y, radius):
                        back += 1
                        if in_p(x, y):
                            mark += 1
            n = SAMPLES * SAMPLES
            alpha = back / n
            mix = mark / back if back else 0
            rgb = [round(p + (w - p) * mix) for p, w in zip(PURPLE, WHITE)]
            row += bytes(rgb + [round(alpha * 255)])
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)     # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


ICONS = {"icon-180.png": (180, 0), "icon-192.png": (192, 22), "icon-512.png": (512, 22),
         "icon-512-maskable.png": (512, 0)}


def main():
    for name, (size, radius) in ICONS.items():
        (SITE / name).write_bytes(draw(size, radius))
        print(f"wrote site/{name}")


if __name__ == "__main__":
    main()
