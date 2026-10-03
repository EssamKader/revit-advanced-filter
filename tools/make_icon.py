# -*- coding: utf-8 -*-
"""Generate the 96x96 funnel icon (stdlib only): python tools/make_icon.py <out.png>"""
import struct
import sys
import zlib

S = 96


def inside(x, y):
    # funnel: trapezoid top, narrow stem
    if 16 <= y <= 46:
        t = (y - 16) / 30.0
        half = 36 - t * 26
        return abs(x - 48) <= half
    if 46 < y <= 80:
        return abs(x - 48) <= 5
    return False


rows = []
for y in range(S):
    row = bytearray([0])
    for x in range(S):
        if inside(x + 0.5, y + 0.5):
            row += bytes((0x2D, 0x9C, 0xDB, 255))
        else:
            row += bytes((0, 0, 0, 0))
    rows.append(bytes(row))


def chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)


png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
with open(sys.argv[1], "wb") as f:
    f.write(png)
