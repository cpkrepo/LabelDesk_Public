#!/usr/bin/env python3
"""Regenerate server/stocks.json — every label the DYMO 550 Turbo / 5XL drivers know — from DYMO's own PPDs
(github.com/dymosoftware/Drivers LW5xx_Linux/ppd; the Mac driver's PPDs have identical pages, diffed 2026-10-10).
  tools/gen-stocks.py [lw550t.ppd lw5xl.ppd]      (no args: downloads them)
Each stock: page (PPD PageSize name), name, size in points (PaperDimension), printable area [l, b, r, t] in points
(ImageableArea), printers that take it. Banners/continuous rolls are left out (no fixed page)."""
import json
import os
import re
import sys
import urllib.request

URL = "https://raw.githubusercontent.com/dymosoftware/Drivers/HEAD/LW5xx_Linux/ppd/{}.ppd"


def read(arg, model):
    if arg:
        return open(arg, encoding="latin-1").read()
    with urllib.request.urlopen(URL.format(model), timeout=30) as r:
        return r.read().decode("latin-1")


def stocks(ppd):
    out = {}
    for kw in ("PaperDimension", "ImageableArea"):
        for m in re.finditer(rf'^\*{kw} ([^/:]+)/([^:]*): "([^"]+)"', ppd, re.M):
            page, name, vals = m.group(1), m.group(2).strip(), [float(v) for v in m.group(3).split()]
            out.setdefault(page, {"page": page, "name": name})[kw] = vals
    return out


def main():
    a = sys.argv[1:] + [None, None]
    t, x = stocks(read(a[0], "lw550t")), stocks(read(a[1], "lw5xl"))
    result, seen = [], set()
    for printer, table in (("550T", t), ("5XL", x)):
        for page, s in table.items():
            if "PaperDimension" not in s or "ImageableArea" not in s or re.search(r"Banner|Continuous", s["name"]):
                continue
            key = (s["name"], tuple(s["PaperDimension"]))
            sku = (re.match(r"(\d{5,7})", s["name"]) or [None, ""])[1]
            if key in seen:                                   # same label in both drivers / twice in one: list once
                for r in result:
                    if (r["name"], tuple(r["size_pt"])) == key and printer not in r["printers"]:
                        r["printers"].append(printer)
                continue
            seen.add(key)
            result.append({"id": page, "page": page, "name": s["name"], "sku": sku, "size_pt": s["PaperDimension"],
                           "area_pt": s["ImageableArea"], "printers": [printer]})
    result.sort(key=lambda r: (r["sku"] == "", r["name"]))
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "stocks.json")
    with open(path, "w") as f:
        json.dump({"source": "DYMO LW5xx_Linux ppd/lw550t.ppd + lw5xl.ppd", "stocks": result}, f, indent=1)
    print(f"{len(result)} stocks → server/stocks.json")


if __name__ == "__main__":
    main()
