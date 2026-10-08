"""Check a shipping label image before it's printed: can a scanner read its tracking barcode?

zbarimg (package zbar) reads the Code 128 barcodes from the exact PNG that would go to the printer. Verified on real
labels 2026-09-30: UPS (1Z…) and FedEx (34-digit barcode whose last 12 digits are the printed tracking number) all read
from LabelDesk's 300 dpi print images. A label with no readable carrier barcode is stopped before printing — it would
fail at the carrier's scanner (blurry screenshot, bad crop).
"""
import re
import shutil
import subprocess
import tempfile

PATTERNS = [                                                    # (carrier, regex on the barcode, tracking from match)
    ("UPS", re.compile(r"^(1Z[0-9A-Z]{16})$"), lambda m: m.group(1)),
    ("FedEx", re.compile(r"^(?:96|10)\d{20}(\d{12})$"), lambda m: m.group(1)),     # 34-digit FedEx barcode
    ("FedEx", re.compile(r"^(\d{12}|\d{15})$"), lambda m: m.group(1)),
    ("USPS", re.compile(r"^(?:420\d{5}(?:\d{4})?)?(9[2-5]\d{18,20})$"), lambda m: m.group(1)),
]


def available():
    return shutil.which("zbarimg") is not None


def codes(png):
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(png)
        f.flush()
        r = subprocess.run(["zbarimg", "--quiet", "--raw", "-Sdisable", "-Scode128.enable", "-Sqrcode.enable",
                            "-Spdf417.enable", f.name], capture_output=True, text=True, timeout=30)
    return [c for c in r.stdout.splitlines() if c.strip()]


def check(png):
    """→ {ok, carrier, tracking, codes, message}. ok = a carrier tracking barcode was read (or zbar isn't installed)."""
    if not available():
        return {"ok": True, "carrier": None, "tracking": None, "codes": [], "message": "barcode check skipped (install zbar)"}
    found = codes(png)
    for c in found:
        for carrier, rx, track in PATTERNS:
            m = rx.match(c.strip())
            if m:
                t = track(m)
                pretty = t if carrier == "UPS" else " ".join(t[i:i + 4] for i in range(0, len(t), 4))
                return {"ok": True, "carrier": carrier, "tracking": pretty, "codes": found, "message": f"{carrier} {pretty}"}
    if found:
        return {"ok": True, "carrier": None, "tracking": None, "codes": found,
                "message": "a barcode reads, but not as a UPS/FedEx/USPS tracking number"}
    return {"ok": False, "carrier": None, "tracking": None, "codes": [],
            "message": "no barcode could be read — the label may be blurry or cut off. Use the carrier's PDF or zoom in "
                       "before the screenshot, or check the crop."}
