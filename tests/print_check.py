#!/usr/bin/env python3
"""End-to-end print check against a RUNNING LabelDesk whose queues point at tests/fake_labelwriter.py: prints a tag and
a 4×6 test pattern the way the page does (PNG + grey pixels), waits until LabelDesk says ✓ Printed, then checks what
the "printer" received — size, margins, and that the label isn't turned or mirrored (a solid block sits top-left).

    python3 tests/fake_labelwriter.py /tmp/ldjobs &   # + queues Dymo-550-Turbo / Dymo-5XL → socket://127.0.0.1:9100
    python3 tests/print_check.py /tmp/ldjobs [--url http://127.0.0.1:8792]

Used by .github/workflows/macos.yml on a real Mac with DYMO Connect for Mac's driver; works on Fedora too.
Reference (Fedora, DYMO's Linux driver, 2026-10-10): tag 304 × 962–963 dots, 4×6 1200 × 1798–1800.
"""
import argparse
import base64
import glob
import json
import os
import struct
import sys
import time
import urllib.request
import zlib

SIZES = {"tag": (298, 962), "ship": (1199, 1799)}                # the canvas sizes the page draws (30252 / 4×6)
EXPECT = {"tag": ((300, 308), (955, 970)), "ship": ((1196, 1204), (1790, 1804))}   # dots received: (w range, h range)


def pattern(w, h):
    """White, a 6-px black frame, a solid block in the top-left (orientation), 8-bit grey rows top to bottom."""
    g = bytearray(b"\xff" * (w * h))
    for y in range(h):
        for x in range(w):
            if x < 6 or y < 6 or x >= w - 6 or y >= h - 6 or (20 < x < w // 3 and 20 < y < h // 6):
                g[y * w + x] = 0
    return bytes(g)


def png(w, h, g):
    raw = b"".join(b"\0" + g[y * w:(y + 1) * w] for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def call(url, path, body=None):
    req = urllib.request.Request(f"{url}/api/{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def runs(seq):
    out, start = [], None
    for i, v in enumerate(list(seq) + [0]):
        if v and start is None:
            start = i
        if not v and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def check_pbm(path, kind):
    data = open(path, "rb").read()
    magic, dims, body = data.split(b"\n", 2)
    w, h = map(int, dims.split())
    stride = (w + 7) // 8
    px = lambda x, y: body[y * stride + x // 8] >> (7 - x % 8) & 1  # noqa: E731
    (wmin, wmax), (hmin, hmax) = EXPECT[kind]
    problems = []
    if not (wmin <= w <= wmax and hmin <= h <= hmax):
        problems.append(f"size {w}×{h}, expected {wmin}–{wmax} × {hmin}–{hmax}")
    row = runs(px(x, 60) for x in range(w))                       # through the block: frame, block, frame
    col = runs(px(50, y) for y in range(h))
    if len(row) != 3 or not (14 <= row[1][0] <= 30):
        problems.append(f"row 60 should be frame · block from x≈21 · frame, got {row[:5]}")
    if len(col) != 3 or not (14 <= col[1][0] <= 30):
        problems.append(f"column 50 should be frame · block from y≈21 · frame, got {col[:5]}")
    return w, h, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", help="the fake printer's output folder")
    ap.add_argument("--url", default="http://127.0.0.1:8792")
    a = ap.parse_args()
    cfg = call(a.url, "config")
    print(f"LabelDesk {cfg['version']} on {cfg['platform']}")
    failed = False
    for kind, (w, h) in SIZES.items():
        before = set(glob.glob(os.path.join(a.jobs, "*.pbm")))
        g = pattern(w, h)
        r = call(a.url, "print", {"kind": kind, "png": "data:image/png;base64," + base64.b64encode(png(w, h, g)).decode(),
                                  "gray": {"w": w, "h": h, "data": base64.b64encode(g).decode()},
                                  "copies": 1, "fields": {"customer": "print check"}, "force": True,
                                  "check": {"ok": True, "tracking": None}})
        state, deadline = {}, time.time() + 120
        while time.time() < deadline:
            state = call(a.url, f"job/{r['id']}")
            if state["state"] in ("done", "failed"):
                break
            time.sleep(1)
        new = sorted(set(glob.glob(os.path.join(a.jobs, "*.pbm"))) - before)
        if state.get("state") != "done" or not new:
            print(f"✗ {kind}: LabelDesk says {state}; new jobs at the printer: {new}")
            failed = True
            continue
        pw, ph, problems = check_pbm(new[-1], kind)
        print(("✗ " if problems else "✓ ") + f"{kind}: printed {pw}×{ph} dots ({os.path.basename(new[-1])})"
              + "".join(f"\n    {p}" for p in problems))
        failed |= bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
