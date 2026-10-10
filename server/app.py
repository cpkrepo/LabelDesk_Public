#!/usr/bin/env python3
"""LabelDesk — DYMO label printing on Fedora, macOS and Windows (a DYMO Connect replacement for the shop's two network printers).

Standard library only. Serves the web app from ../web and a JSON API. Labels are drawn in the browser at the printer's
300 dpi (what you see is exactly what prints); the server hands the PNG to CUPS with `lp` (macOS: the grey pixels as an
exact-size PDF, see label_pdf), follows the job until the
printer has finished (ipp.py) and explains problems in plain English, checks shipping labels' barcodes before they
print (the browser with ZXing; barcode.py/zbar double-checks on Fedora), keeps a history for reprints, and watches
for new labels (inbox.py: Downloads + the
"Shipping Label (LabelDesk)" print-dialog printer).

Printers are CUPS queues set up by tools/add-printers.sh (DYMO's official 550-series driver, tools/install-driver.sh):
  tag      → LabelWriter 550 Turbo, 30252 Address (1-1/8" × 3-1/2", page "w79h252") — or 30321 Large Address
             (1.4" × 3.5", page "w102h252"), chosen in Settings (config tag_label)
  shipping → LabelWriter 5XL, 4" × 6" (1744907), page "1744907_4_in_x_6_in"
Config: environment or ~/.config/labeldesk/config.json {"tag_queue", "ship_queue", "bind", "port", "flip_tag", "tag_offset_mm",
"watch_downloads"}.
"""
import base64
import hashlib
import json
import mimetypes
import os
import ipaddress
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import autoprint
import barcode
import sheet
import connectwise
import dymo
import keys
from inbox import SPOOL, Inbox, downloads_dir

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"                                   # CUPS like Fedora, DYMO Connect for Mac's driver
if WINDOWS:
    import winprint                                              # DYMO's Windows driver (DYMO Connect's), via ctypes
else:
    import ipp                                                   # CUPS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, ".."))


def _read_version():
    """The one place the version lives: VERSION at the top of the checkout (the Windows build copies it beside server/)."""
    try:
        with open(os.path.join(ROOT, "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


VERSION = _read_version()
STARTED = time.time()                                            # the page sees a restart by this changing
# after each print the app asks GitHub for the newest VERSION (a plain GET of one small file; no label content, no IDs)
REPO = "cpkrepo/LabelDesk_Public"
UPDATE_URL = f"https://raw.githubusercontent.com/{REPO}/main/VERSION"
RELEASES_URL = f"https://github.com/{REPO}/releases"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/tags/v{{version}}"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases?per_page=40"
UPGRADE_CODE = "{6B9C2E31-4A57-4D3F-9E1B-2F7C5A0D8E41}"         # windows/labeldesk.wxs — fixed forever
WEB = os.path.realpath(os.environ.get("LABELDESK_WEB") or os.path.join(HERE, "..", "web"))
if WINDOWS:
    CONF_FILE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LabelDesk", "config.json")
    DATA = os.environ.get("LABELDESK_DATA", os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LabelDesk"))
elif MAC:
    CONF_FILE = os.path.expanduser("~/Library/Application Support/LabelDesk/config.json")
    DATA = os.environ.get("LABELDESK_DATA", os.path.expanduser("~/Library/Application Support/LabelDesk"))
else:
    CONF_FILE = os.path.expanduser("~/.config/labeldesk/config.json")
    DATA = os.environ.get("LABELDESK_DATA", os.path.expanduser("~/.local/share/labeldesk"))
CONF_DIR = os.path.dirname(CONF_FILE)
MAX_BODY = 25 * 1024 * 1024          # a pasted screenshot or PDF
MAX_LOGO = 2 * 1024 * 1024
KEEP_SHIP_IMAGES = 200               # shipping labels kept for reprint

# the label kinds the shop prints — page names, sizes and printable areas (ImageableArea) from DYMO's lw550t.ppd / lw5xl.ppd
TAG_STOCKS = {
    "30252": {"name": "Inventory tag", "stock": "30252 Address", "size": "1-1/8\" × 3-1/2\"", "page": "w79h252",
              "width_in": 79 / 72, "height_in": 252 / 72, "safe_in": [4.32 / 72, 4.32 / 72, 76.08 / 72, 235.44 / 72]},
    "30321": {"name": "Inventory tag", "stock": "30321 Large Address", "size": "1.4\" × 3.5\"", "page": "w102h252",
              "width_in": 102 / 72, "height_in": 251 / 72, "safe_in": [4.32 / 72, 3.84 / 72, 98.40 / 72, 234.48 / 72]},
}
DEFAULT_TAG_STOCK = "30252"          # the shop's roll, measured 2026-10-08 (1-1/8" × 3-1/2")
LABELS = {
    "tag": TAG_STOCKS[DEFAULT_TAG_STOCK],
    "ship": {"name": "Shipping label", "stock": "1744907 4 × 6", "page": "1744907_4_in_x_6_in",
             "width_in": 296 / 72, "height_in": 452 / 72, "safe_in": [4.08 / 72, 4.08 / 72, 292.08 / 72, 436.08 / 72]},
}


def config():
    c = {"tag_queue": "Dymo-550-Turbo", "ship_queue": "Dymo-5XL", "bind": "127.0.0.1", "port": 8792, "flip_tag": False, "tag_offset_mm": 0,
         "watch_downloads": True, "update_check": True, "update_url": UPDATE_URL, "tag_logo": "",
         "tag_label": DEFAULT_TAG_STOCK, "auto_printers": True, "tag_barcode": "code128",
         "auto_ship": False}
    try:
        with open(CONF_FILE) as f:
            c.update(json.load(f))
    except (OSError, ValueError):
        pass
    for k in ("tag_queue", "ship_queue", "bind"):
        c[k] = os.environ.get("LABELDESK_" + k.upper(), c[k])
    c["port"] = int(os.environ.get("LABELDESK_PORT", c["port"]))
    if os.environ.get("LABELDESK_WATCH") == "0":
        c["watch_downloads"] = False
    if os.environ.get("LABELDESK_AUTO_PRINTERS") == "0":
        c["auto_printers"] = False
    return c


_found = {}


def queue_for(kind):
    """The CUPS queue (Fedora) or Windows printer name for a label kind. Windows: the DYMO 550 Turbo / 5XL installed
    with DYMO Connect, found by name — config tag_printer / ship_printer override."""
    cfg = config()
    if WINDOWS:
        override = cfg.get("tag_printer" if kind == "tag" else "ship_printer")
        if override:
            return override
        if not _found.get(kind):
            try:
                _found.update({k: v for k, v in winprint.find().items() if k in ("tag", "ship") and v})
            except RuntimeError:
                pass
        return _found.get(kind) or ""
    return cfg["tag_queue"] if kind == "tag" else cfg["ship_queue"]


# ------------------------------------------------------------------ history (SQLite)
LOCK = threading.Lock()
COLUMNS = {"state": "TEXT", "message": "TEXT", "image": "TEXT", "tracking": "TEXT",
           "collected": "TEXT"}                                     # 0.10: picked up (History → Scan a tag), this PC only


_schema_ok = []


def db():
    os.makedirs(DATA, exist_ok=True)
    c = sqlite3.connect(os.path.join(DATA, "labeldesk.db"), timeout=10)
    c.row_factory = sqlite3.Row
    if not _schema_ok:                                            # once per process: create / upgrade the table
        os.makedirs(DATA, exist_ok=True)
        c.execute("CREATE TABLE IF NOT EXISTS printed(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, at TEXT NOT NULL, "
                  "copies INTEGER NOT NULL, fields TEXT NOT NULL, queue TEXT, job TEXT)")
        have = {r["name"] for r in c.execute("PRAGMA table_info(printed)")}
        for col, typ in COLUMNS.items():                         # 0.3: job state, shipping image, tracking number
            if col not in have:
                c.execute(f"ALTER TABLE printed ADD COLUMN {col} {typ}")
        c.commit()
        _schema_ok.append(True)
    return c


def row(hid):
    c = db()
    r = c.execute("SELECT * FROM printed WHERE id=?", (hid,)).fetchone()
    c.close()
    return dict(r) if r else None


def history(limit=80, q="", kind="", since="", until="", before=0, ticket="", serial=""):
    """Printed labels, newest first, searched over EVERYTHING ever printed on this PC: q matches any field (customer,
    company, ticket, serial, bin, free text…) or the tracking number; kind tag/ship; since/until YYYY-MM-DD (inclusive);
    before = an id, for "Show more"."""
    where, args = [], []
    if q.strip():
        esc_like = lambda t: "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"   # noqa: E731
        # fields are stored by json.dumps (non-ASCII as \\uXXXX, quotes escaped): search them in that form
        where.append("(fields LIKE ? ESCAPE '\\' OR IFNULL(tracking, '') LIKE ? ESCAPE '\\')")
        args += [esc_like(json.dumps(q.strip())[1:-1]), esc_like(q.strip())]
    if kind in ("tag", "ship"):
        where.append("kind = ?"); args.append(kind)
    for key, val in (("ticket", ticket), ("serial", serial)):          # exact field (as json.dumps wrote it)
        if val.strip():
            where.append("fields LIKE ? ESCAPE '\\'")
            args.append("%" + json.dumps({key: val.strip()})[1:-1].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if since:
        where.append("at >= ?"); args.append(since)
    if until:
        where.append("at < ?"); args.append(until + "T99")                # the whole 'until' day
    if before:
        where.append("id < ?"); args.append(int(before))
    sql = "SELECT * FROM printed" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    c = db()
    rows = [dict(r) | {"fields": json.loads(r["fields"])} for r in c.execute(sql, (*args, int(limit)))]
    c.close()
    return rows


HISTORY_CSV = ["when", "label", "customer", "company", "ticket", "received", "serial", "bin", "text", "tracking", "copies",
               "printed"]


def history_csv(**filters):
    """The same search as a spreadsheet (Excel / Numbers / LibreOffice open it)."""
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HISTORY_CSV)
    for r in history(limit=100000, **filters):
        f = r["fields"]
        w.writerow([r["at"].replace("T", " "), "Inventory tag" if r["kind"] == "tag" else "Shipping label",
                    f.get("customer", ""), f.get("company", ""), f.get("ticket", ""), f.get("received", ""),
                    f.get("serial", ""), f.get("bin", ""), (f.get("free") or "").replace("\n", " / "), r.get("tracking") or "",
                    r["copies"], {"done": "yes", "failed": "no"}.get(r.get("state"), r.get("state") or "")])
    return "\ufeff" + out.getvalue()                                  # BOM: Excel reads it as UTF-8


def device_info(serial):
    """Been here before? This PC's earlier tags with this serial (+ ConnectWise configurations with it when it's on)."""
    seen = [r for r in history(limit=20, serial=serial) if r["kind"] == "tag" and (r["fields"].get("serial") or "").lower() == serial.strip().lower()]
    out = {"serial": serial.strip(), "before": [{"at": r["at"], "ticket": r["fields"].get("ticket", ""), "customer": r["fields"].get("customer", ""),
                                                 "collected": r.get("collected")} for r in seen], "cw": []}
    st = cw_status()
    if st["on"]:
        try:
            out["cw"] = connectwise.device(cw_creds(), serial)
        except (connectwise.CWError, LookupError, OSError) as e:
            out["cwError"] = str(e)
    return out


def ticket_info(number):
    """Scan a tag (History): everything printed for this ticket here, picked up or not, + the ConnectWise ticket."""
    n = str(number).strip().lstrip("#")
    rows = [r for r in history(limit=200, ticket=n) if r["fields"].get("ticket") == n]
    out = {"ticket": n, "tags": rows, "collected": next((r["collected"] for r in rows if r.get("collected")), None), "cw": None}
    if cw_status()["on"]:
        try:
            out["cw"] = connectwise.ticket(cw_creds(), n)
        except LookupError:
            out["cw"] = None
        except (connectwise.CWError, OSError) as e:
            out["cwError"] = str(e)
    return out


def set_collected(number, collected):
    n = str(number).strip().lstrip("#")
    c = db()
    with c:
        c.execute("UPDATE printed SET collected = ? WHERE kind = 'tag' AND fields LIKE ? ESCAPE '\\'",
                  (datetime.now().isoformat(timespec="seconds") if collected else None,
                   "%" + json.dumps({"ticket": n})[1:-1].replace("%", "\\%").replace("_", "\\_") + "%"))
    c.close()


def customers(limit=400):
    """Customer names from past tags, most recently used first (for autocomplete)."""
    c = db()
    seen, out = set(), []
    for r in c.execute("SELECT fields FROM printed WHERE kind='tag' ORDER BY id DESC LIMIT 3000"):
        name = (json.loads(r["fields"]).get("customer") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
            if len(out) >= limit:
                break
    c.close()
    return out


def update(hid, **cols):
    with LOCK:
        c = db()
        with c:
            c.execute(f"UPDATE printed SET {', '.join(k + '=?' for k in cols)} WHERE id=?", (*cols.values(), hid))
        c.close()


def keep_image(hid, png):
    d = os.path.join(DATA, "ship")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{hid}.png")
    with open(path, "wb") as f:
        f.write(png)
    old = sorted((int(n[:-4]) for n in os.listdir(d) if n[:-4].isdigit()), reverse=True)[KEEP_SHIP_IMAGES:]
    for n in old:
        try:
            os.unlink(os.path.join(d, f"{n}.png"))
        except OSError:
            pass
    return path


# ------------------------------------------------------------------ CUPS
RECENT = {}                          # png hash → time: a second identical print within 3 s is a double press


def submit(kind, png_bytes, copies, gray=None, lab=None):
    """Hand one label to the printer. Fedora: the PNG through CUPS (lp). Windows: the 8-bit grey image through DYMO's
    Windows driver (winprint). → (queue/printer, job id)."""
    if WINDOWS:
        printer = queue_for(kind)
        if not printer:
            raise RuntimeError(f"no DYMO {'550 Turbo' if kind == 'tag' else '5XL'} printer on this PC — add it in DYMO Connect "
                               "or Windows Settings → Printers")
        if not gray:
            raise ValueError("the Windows version needs the label as grey pixels (update LabelDesk)")
        designed = lab is not None
        lab = lab or labels()[kind]
        sku = lab["stock"].split()[0]
        job, _paper = winprint.submit(printer, kind, gray, copies, f"LabelDesk {lab['name']}",
                                      paper=(sku,) if (kind == "tag" or designed) and sku[:1].isdigit() else None)
        return printer, job
    if MAC and gray:
        return lp(kind, label_pdf(lab or labels()[kind], *gray), copies, ".pdf", lab)
    return lp(kind, png_bytes, copies, lab=lab)


def label_pdf(lab, w, h, gray):
    """The label as a one-page PDF exactly the label's page size, the w×h grey pixels placed at 300 dpi, centred in the
    printable area — where `lp -o ppi=300 -o position=center` puts the PNG on Fedora. macOS prints images through its
    own filters (which don't promise to honour ppi/position); a PDF of the right page size prints 1:1 everywhere."""
    import zlib
    pw, ph = round(lab["width_in"] * 72, 2), round(lab["height_in"] * 72, 2)
    left, bottom, right, top = (v * 72 for v in lab["safe_in"])
    iw, ih = w * 72 / 300, h * 72 / 300
    x, y = left + (right - left - iw) / 2, bottom + (top - bottom - ih) / 2
    content = f"q {iw:.3f} 0 0 {ih:.3f} {x:.3f} {y:.3f} cm /Im0 Do Q".encode()
    image = zlib.compress(gray)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:g} {ph:g}] /Resources << /XObject << /Im0 4 0 R >> >> "
            f"/Contents 5 0 R >>".encode(),
            f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray /BitsPerComponent 8 "
            f"/Filter /FlateDecode /Length {len(image)} >>\nstream\n".encode() + image + b"\nendstream",
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"]
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def lp(kind, data, copies, suffix=".png", lab=None):
    """Send one label (PNG, or the exact-size PDF from label_pdf) to its queue at exactly 300 dpi on the right page
    size. → (queue, job number)."""
    queue = queue_for(kind)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        lab = lab or labels()[kind]
        opts = ["-o", "ppi=300", "-o", "position=center"] if suffix == ".png" else []
        r = subprocess.run(["lp", "-d", queue, "-n", str(copies), "-t", f"LabelDesk {lab['name']}",
                            "-o", f"PageSize={lab['page']}", *opts, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip() or "lp failed"
        if "does not exist" in msg:
            msg = f"the printer queue {queue} isn't set up on this PC — run tools/add-printers.sh"
        elif "not accepting" in msg:
            msg = f"{queue} isn't accepting jobs — press Resume"
        raise RuntimeError(msg)
    m = re.search(r"request id is \S+-(\d+)", r.stdout)
    return queue, m.group(1) if m else ""


def print_label(kind, png, copies, fields, force=False, gray=None, client_check=None, stock=None):
    lab = stock_label(stock) if stock else None                   # the designer: any DYMO label (stocks.json)
    if lab and ("550T" if kind == "tag" else "5XL") not in lab["printers"]:
        raise ValueError(f"the {'550 Turbo' if kind == 'tag' else '5XL'} doesn't take {lab['name']} labels")
    digest = hashlib.sha1(png + f"{kind}:{copies}".encode()).hexdigest()
    if not force and time.time() - RECENT.get(digest, 0) < 3:
        return {"duplicate": True, "error": "that label was just sent — press Print again to print another"}, 409
    check = None
    if kind == "ship" and not lab:                                # a designed label on the 5XL isn't a carrier label
        # zbar here (Fedora) double-checks; without it (Windows) the browser's ZXing check stands
        check = barcode.check(png) if barcode.available() else (client_check or {"ok": True, "tracking": None})
        if not check.get("ok") and not force:
            return {"needsForce": True, "check": check, "error": check.get("message", "no barcode could be read")}, 422
    if not force:
        why = roll_check(kind, lab["sku"] if lab else None)
        if why:
            return {"needsForce": True, "roll": True, "error": why}, 422
    with LOCK:
        c = db()
        with c:
            hid = c.execute("INSERT INTO printed(kind, at, copies, fields, state, tracking) VALUES(?,?,?,?,?,?)",
                            (kind, datetime.now().isoformat(timespec="seconds"), copies, json.dumps(fields), "sending",
                             (check or {}).get("tracking"))).lastrowid
        c.close()
    if kind == "ship":
        update(hid, image=keep_image(hid, png))
    try:
        queue, job = submit(kind, png, copies, gray, lab)
    except RuntimeError as e:
        update(hid, state="failed", message=str(e))
        raise
    now = time.time()
    for k in [k for k, t in RECENT.items() if now - t > 10]:
        del RECENT[k]
    RECENT[digest] = now
    update(hid, queue=queue, job=job, state="sent")
    return {"id": hid, "queue": queue, "job": job, "check": check}, 200


def job_status(hid):
    """Where is history entry `hid` now? done / waiting / failed + a plain-English message. A failed job is cancelled,
    so it can't come out unexpectedly later when the printer is back (the app offers Print again instead)."""
    r = row(hid)
    if not r:
        raise KeyError("no such print")
    if r["state"] in ("done", "failed") or not r["job"]:
        return {"state": r["state"], "message": r["message"] or ""}
    if WINDOWS:
        try:
            s = winprint.job(r["queue"], r["job"])
        except RuntimeError as e:
            return {"state": "waiting", "message": str(e)}
        if s["state"] == "failed":
            why = win_plain(s)
            winprint.cancel(r["queue"], r["job"])
            update(hid, state="failed", message=why)
            return {"state": "failed", "message": why}
        if s["state"] == "done":
            update(hid, state="done", message="")
            return {"state": "done", "message": ""}
        return {"state": "waiting", "message": win_plain(s) if s.get("flags") else s["message"]}
    try:
        j = ipp.job(r["queue"], r["job"])
    except (OSError, LookupError) as e:
        return {"state": "waiting", "message": f"can't reach CUPS ({e})"}
    try:
        p = ipp.printer(r["queue"])
    except (OSError, LookupError):
        p = {"reasons": [], "message": "", "state": "unknown", "accepting": True}
    if j["state"] == "completed":
        update(hid, state="done", message="")
        return {"state": "done", "message": ""}
    if j["state"] in ("stopped", "aborted", "canceled"):
        why = ipp.plain(p["reasons"], j["message"] or p["message"]) or "the printer reported an error"
        subprocess.run(["cancel", f"{r['queue']}-{r['job']}"], capture_output=True)
        update(hid, state="failed", message=why)
        return {"state": "failed", "message": why}
    why = ipp.plain(p["reasons"], j["message"] or p["message"])       # pending/processing: say what it's waiting on
    return {"state": "waiting", "message": why or ("printing…" if j["state"] == "processing" else "queued…")}


WIN_PLAIN = {"paper out": "out of labels — load a new roll", "offline": "the printer is offline — check power and the network cable",
             "error": "the printer reported an error — check it (lid, roll, lights)", "paused": "printing is paused on this PC",
             "paper jam": "labels jammed — open the printer and clear it", "door open": "the printer's cover is open",
             "needs attention": "the printer needs attention — check it", "blocked": "the job is blocked — check the printer"}


def win_plain(s):
    """Windows job/printer flags + the driver's status text → plain English (the DYMO driver's own text wins)."""
    text = (s.get("message") or "").strip()
    flags = s.get("flags") or s.get("reasons") or []
    for f in ("paper out", "offline", "paper jam", "door open", "paused", "blocked", "needs attention", "error"):
        if f in flags:
            return WIN_PLAIN[f] + (f" ({text})" if text and text.lower() != f else "")
    return text


def version_tuple(v):
    """'0.6.10' → (0, 6, 10); anything unparseable → () so it never counts as newer."""
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return ()


_update = {"at": 0, "result": None}
UPDATE_CACHE_S = 60                  # a batch of tags asks once, not once per tag


def check_update(cfg=None, now=None):
    """→ {enabled, current, latest, newer, error, how, command}. Asked after every print; cached for a minute."""
    cfg = cfg or config()
    res = {"enabled": bool(cfg.get("update_check", True)), "current": VERSION, "latest": None, "newer": False,
           "error": None, "how": "windows" if WINDOWS else ("git" if os.path.isdir(os.path.join(ROOT, ".git")) else "folder"),
           "releases": RELEASES_URL, "command": f"cd {ROOT} && tools/update.sh", "local": None, "canUpdateNow": False}
    if res["how"] == "git":
        res["local"] = git_state()
        res["canUpdateNow"] = bool(res["local"]) and not res["local"]["dirty"] and not res["local"]["ahead"] \
            and (MAC or bool(shutil.which("systemd-run")))
    res["canInstall"] = res["how"] == "windows"
    res["held"] = cfg.get("hold_version") or None                 # Settings → Version: this PC stays on a chosen one
    if not res["enabled"] or res["held"]:
        return res
    now = time.time() if now is None else now
    if _update["result"] and now - _update["at"] < UPDATE_CACHE_S:
        return _update["result"]
    try:
        req = urllib.request.Request(cfg.get("update_url") or UPDATE_URL, headers={"User-Agent": f"LabelDesk/{VERSION}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            latest = r.read(64).decode("ascii", "replace").strip().splitlines()[0].strip()
        if not version_tuple(latest):
            raise ValueError(f"unexpected version text {latest[:20]!r}")
        res["latest"] = latest
        res["newer"] = version_tuple(latest) > version_tuple(VERSION)
    except Exception as e:                                       # offline, GitHub down, repo private: just say so
        res["error"] = str(e)[:200]
    _update.update(at=now, result=res)
    return res


# every DYMO label the 550 / 5XL drivers know (tools/gen-stocks.py → stocks.json) — the designer prints on any of them
def _load_stocks():
    try:
        with open(os.path.join(HERE, "stocks.json")) as f:
            return {s["id"]: s for s in json.load(f)["stocks"]}
    except (OSError, ValueError, KeyError):
        return {}


STOCKS = _load_stocks()


def stock_label(stock_id):
    """A stocks.json label in the same shape as LABELS entries (page, inches, printable area). KeyError if unknown."""
    s = STOCKS[stock_id]
    w, h = s["size_pt"]
    return {"name": s["name"], "stock": s["name"], "page": s["page"], "size": s["name"].split(" ", 1)[-1],
            "width_in": w / 72, "height_in": h / 72, "safe_in": [v / 72 for v in s["area_pt"]], "sku": s["sku"],
            "printers": s["printers"]}


# ---- shop templates: designer layouts shared through the repo (templates/*.json — reviewed like any change)
TEMPLATES_DIR = os.environ.get("LABELDESK_TEMPLATES") or os.path.join(ROOT, "templates")


def shared_templates():
    out = []
    try:
        names = sorted(n for n in os.listdir(TEMPLATES_DIR) if n.endswith(".json"))
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(TEMPLATES_DIR, n), encoding="utf-8") as f:
                t = json.load(f)
            if isinstance(t, dict) and isinstance(t.get("objects"), list):
                out.append({**t, "id": "shop:" + n[:-5], "shared": True})
        except (OSError, ValueError):
            continue
    return out


def share_template(t):
    """Settings-free sharing: write the layout into the checkout's templates/ — tools/update.sh then sends it to the owner
    as a pull request (Fedora/Mac). Pictures are refused: the repo is public (logos stay per PC)."""
    if WINDOWS or not os.path.isdir(os.path.join(ROOT, ".git")):
        raise ValueError("sharing needs a Fedora or Mac PC with LabelDesk from GitHub — use Export and send the file instead")
    if not isinstance(t, dict) or not isinstance(t.get("objects"), list) or not str(t.get("name") or "").strip():
        raise ValueError("send a template with a name")
    if any(o.get("kind") == "image" for o in t["objects"]):
        raise ValueError("templates with pictures can't be shared — the repo is public (logos stay on each PC). Remove the picture first")
    slug = re.sub(r"[^a-z0-9]+", "-", t["name"].strip().lower()).strip("-")[:60] or "template"
    keep = {k: t[k] for k in ("name", "stock", "orientation", "rect", "objects", "flip") if k in t}
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    path = os.path.join(TEMPLATES_DIR, slug + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(keep, f, indent=1, ensure_ascii=False)
        f.write("\n")
    return os.path.relpath(path, ROOT)


def labels(cfg=None):
    """The label kinds with the tag stock this PC is set to (Settings → Tag labels; config tag_label)."""
    stock = str((cfg or config()).get("tag_label") or DEFAULT_TAG_STOCK)
    return {**LABELS, "tag": TAG_STOCKS.get(stock, TAG_STOCKS[DEFAULT_TAG_STOCK])}


def save_config(**changes):
    """Merge `changes` into config.json (keeps everything else in it)."""
    try:
        with open(CONF_FILE) as f:
            cur = json.load(f)
    except (OSError, ValueError):
        cur = {}
    cur.update(changes)
    os.makedirs(CONF_DIR, exist_ok=True)
    tmp = CONF_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cur, f, indent=2)
    os.replace(tmp, CONF_FILE)


# ---- the shop's logo on the built-in tag: kept per PC (config folder), never in the repo -------------------------------
def logo_path(cfg=None):
    return (cfg or config()).get("tag_logo") or os.path.join(CONF_DIR, "tag-logo.png")


def migrate_logo():
    """Installs from before 0.6.1 had the logo at web/tag-logo.png: copy it to the config folder once, if it's there."""
    old, new = os.path.join(WEB, "tag-logo.png"), logo_path()
    if os.path.isfile(old) and not os.path.exists(new):
        os.makedirs(os.path.dirname(new), exist_ok=True)
        shutil.copyfile(old, new)


def save_logo(url):
    mime, raw = data_url(url)
    if mime not in ("image/png", "image/jpeg") or not (raw[:4] == b"\x89PNG" or raw[:3] == b"\xff\xd8\xff"):
        raise ValueError("the logo must be a PNG or JPEG image")
    if len(raw) > MAX_LOGO:
        raise ValueError("the logo file is too big (2 MB max)")
    path = logo_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)


# ---- updating from the app ---------------------------------------------------------------------------------------------
def git_state():
    """→ {dirty, ahead} of this checkout (no network). None when it isn't a git checkout or git is missing."""
    if not os.path.isdir(os.path.join(ROOT, ".git")) or not shutil.which("git"):
        return None
    try:
        run = lambda *a: subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True, timeout=10)   # noqa: E731
        dirty = bool(run("status", "--porcelain", "--untracked-files=no").stdout.strip())
        r = run("rev-list", "--count", "origin/main..HEAD")
        return {"dirty": dirty, "ahead": int(r.stdout.strip() or 0) if r.returncode == 0 else 0}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def update_log():
    return os.path.join(DATA, "update.log")


def run_update_now():
    """Fedora "Update now": only when this PC has no unpushed changes (then update.sh just fast-forwards and restarts —
    no push, no merge). Runs outside LabelDesk's own service so the restart at the end doesn't cut it off."""
    if WINDOWS:
        raise ValueError("on Windows the update is the new installer (Install update)")
    st = git_state()
    if st is None:
        raise ValueError("this copy isn't a git checkout — reinstall from GitHub (SETUP.md section 1)")
    if st["dirty"] or st["ahead"]:
        raise ValueError(f"this PC has changes that aren't on GitHub yet — run tools/update.sh in {ROOT} so they're merged")
    run_detached("tools/update.sh")


def run_detached(tool):
    """Run `tool` (relative to the checkout) outside LabelDesk, logging to update.log, so the restart at its end doesn't
    cut it off: Mac in its own session (launchd), Fedora in its own systemd unit (the service's cgroup gets killed)."""
    os.makedirs(DATA, exist_ok=True)
    cmd = f"cd {shlex_quote(ROOT)} && {tool} > {shlex_quote(update_log())} 2>&1"
    if MAC:
        subprocess.Popen(["/bin/bash", "-c", cmd], start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if not shutil.which("systemd-run"):
        raise ValueError(f"systemd-run isn't available — run {tool} in a Terminal in {ROOT}")
    subprocess.run(["systemd-run", "--user", "--collect", "--quiet", f"--unit=labeldesk-update-{int(time.time())}",
                    "/bin/bash", "-c", cmd], check=True, capture_output=True, timeout=15)


# ---- Settings → Version: any published version on this PC (held there), or — owner only — for every PC
_versions = {"at": 0, "list": None}


def published_versions(now=None):
    """GitHub's releases, newest first: [{version, date, notes, msi}] (cached 10 min). Raises when GitHub can't be reached."""
    now = time.time() if now is None else now
    if _versions["list"] is not None and now - _versions["at"] < 600:
        return _versions["list"]
    rels = json.loads(download(RELEASES_API, 5_000_000, "application/vnd.github+json"))
    out = []
    for r in rels:
        v = str(r.get("tag_name") or "").lstrip("v")
        if not version_tuple(v) or r.get("draft"):
            continue
        notes = [ln.strip()[2:] for ln in (r.get("body") or "").splitlines() if ln.strip().startswith("- ")]
        names = {a.get("name") for a in r.get("assets", [])}
        out.append({"version": v, "date": (r.get("published_at") or "")[:10], "notes": notes[:6],
                    "msi": f"LabelDesk-{v}.msi" in names and f"LabelDesk-{v}.msi.sha256" in names})
    out.sort(key=lambda x: version_tuple(x["version"]), reverse=True)
    _versions.update(at=now, list=out)
    return out


_publisher = {}


def is_publisher():
    """The repo's owner (GitHub admin, or git config labeldesk.publisher true) — the only one who publishes versions."""
    if "v" not in _publisher:
        ok = False
        try:
            r = subprocess.run(["git", "-C", ROOT, "config", "--get", "labeldesk.publisher"], capture_output=True, text=True, timeout=5)
            ok = r.stdout.strip() == "true"
            if not ok and shutil.which("gh"):
                r = subprocess.run(["gh", "api", f"repos/{REPO}", "--jq", ".permissions.admin"], capture_output=True, text=True, timeout=15)
                ok = r.stdout.strip() == "true"
        except (OSError, subprocess.SubprocessError):
            pass
        _publisher["v"] = ok
    return _publisher["v"]


def versions_info():
    cfg = config()
    info = {"current": VERSION, "held": cfg.get("hold_version") or None, "platform": "windows" if WINDOWS else "mac" if MAC else "linux",
            "how": "windows" if WINDOWS else ("git" if os.path.isdir(os.path.join(ROOT, ".git")) else "folder"),
            "publisher": (not WINDOWS) and is_publisher(), "versions": [], "error": None}
    try:
        vs = published_versions()
    except Exception as e:                                        # noqa: BLE001 — offline: say so
        info["error"] = f"couldn't reach GitHub ({e})"
        return info
    floor = (0, 8, 0) if MAC else (0, 0, 0)
    for v in vs:
        v = dict(v, installable=(v["msi"] if WINDOWS else version_tuple(v["version"]) >= floor), current=v["version"] == VERSION)
        info["versions"].append(v)
    info["newest"] = vs[0]["version"] if vs else None
    return info


def use_version(version, everyone=False):
    """Settings → Version → Use this version (this PC, held there) / newest (follow updates again) / for every PC."""
    version = str(version or "").strip().lstrip("v")
    if version != "newest" and not version_tuple(version):
        raise ValueError("pick a version")
    if WINDOWS:
        if everyone:
            raise ValueError("publishing a version for every PC is done from the owner's Fedora/Mac PC")
        target = published_versions()[0]["version"] if version == "newest" else version
        save_config(hold_version=None if version == "newest" else target)
        if target == VERSION:
            return
        return install_windows_version(target)
    st = git_state()
    if st is None:
        raise ValueError("this copy isn't a git checkout — reinstall it from GitHub (SETUP.md section 1)")
    if st["dirty"] or st["ahead"]:
        raise ValueError(f"this PC has changes that aren't on GitHub yet — run tools/update.sh in {ROOT} first")
    if everyone and not is_publisher():
        raise ValueError("only the owner publishes versions — ask with a \"Please roll back\" issue on GitHub")
    run_detached(f"tools/switch-version.sh {version}" + (" --everyone" if everyone else ""))


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


def download(url, limit, accept="application/octet-stream"):
    req = urllib.request.Request(url, headers={"User-Agent": f"LabelDesk/{VERSION}", "Accept": accept})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError(f"download bigger than expected: {url}")
    return data


def install_windows_update(version):
    """Windows "Install update": a NEWER version (install_windows_version does the work)."""
    if not WINDOWS:
        raise ValueError("on Fedora use Update now / tools/update.sh")
    if not version_tuple(version) or version_tuple(version) <= version_tuple(VERSION):
        raise ValueError("no newer version to install")
    install_windows_version(version)


def install_windows_version(version):
    """The MSI for `version` from the GitHub release, checked against the release's .sha256, installed per user (no
    admin) by a helper that waits for this server to exit, then starts it again. An OLDER version: the installed one is
    uninstalled first (an older MSI doesn't replace a newer one; settings and history in %APPDATA% stay)."""
    if not WINDOWS:
        raise ValueError("Windows only")
    rel = json.loads(download(RELEASE_API.format(version=version), 1_000_000, "application/vnd.github+json"))
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    msi_name = f"LabelDesk-{version}.msi"
    if msi_name not in assets or msi_name + ".sha256" not in assets:
        raise RuntimeError(f"the {version} release has no {msi_name} (+ .sha256) yet — try again later")
    want = download(assets[msi_name + ".sha256"], 10_000).decode("ascii", "replace").split()[0].lower()
    msi = download(assets[msi_name], 200_000_000)
    got = hashlib.sha256(msi).hexdigest()
    if got != want:
        raise RuntimeError("the downloaded installer doesn't match its checksum — not installed")
    work = os.path.join(DATA, "update")
    os.makedirs(work, exist_ok=True)
    msi_path = os.path.join(work, msi_name)
    with open(msi_path, "wb") as f:
        f.write(msi)
    pythonw = os.path.join(ROOT, "python", "pythonw.exe")
    server = os.path.join(ROOT, "labeldesk-server.pyw")
    log = os.path.join(work, "install.log")
    older = version_tuple(version) < version_tuple(VERSION)
    # Windows Installer's own list of LabelDesk installs (by the fixed UpgradeCode in windows/labeldesk.wxs) — per-user
    # MSIs aren't in the Uninstall registry key (found on the test VM)
    remove = ("$wi = New-Object -ComObject WindowsInstaller.Installer; "
              f"foreach ($c in @($wi.RelatedProducts('{UPGRADE_CODE}'))) "
              "{ Start-Process msiexec.exe -ArgumentList '/x',$c,'/qb' -Wait }; ") if older else ""
    ps = (f"Wait-Process -Id {os.getpid()} -Timeout 60 -ErrorAction SilentlyContinue; {remove}"
          f"$p = Start-Process msiexec.exe -ArgumentList '/i','\"{msi_path}\"','/qb','/l*v','\"{log}\"' -Wait -PassThru; "
          f"Start-Process '{pythonw}' -ArgumentList '\"{server}\"'; exit $p.ExitCode")
    script = os.path.join(work, "install-update.ps1")
    with open(script, "w", encoding="utf-8") as f:
        f.write(ps + "\n")
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script]
    # CREATE_NO_WINDOW (a hidden console — PowerShell started DETACHED_PROCESS, i.e. with no console, quits at once:
    # "Install update" never ran that way, found on the test VM 2026-10-10) | CREATE_NEW_PROCESS_GROUP |
    # CREATE_BREAKAWAY_FROM_JOB (outlive LabelDesk even if it was started inside a job, e.g. by a scheduled task)
    try:
        subprocess.Popen(args, creationflags=0x08000000 | 0x00000200 | 0x01000000, close_fds=True)
    except OSError:                                                      # the job doesn't allow breaking away
        subprocess.Popen(args, creationflags=0x08000000 | 0x00000200, close_fds=True)
    threading.Timer(1.0, lambda: os._exit(0)).start()                   # let the reply go out, then free the files


# ---- Windows: printers that discovery can't find (Settings → Printers by IP) -------------------------------------------
def windows_script(name):
    return os.path.join(ROOT, name)


def check_ips(ips):
    out = []
    for ip in ips:
        out.append(str(ipaddress.ip_address(ip.strip())))
    if not out:
        raise ValueError("give at least one printer IP")
    return out


def windows_printer_check(ips):
    ips = check_ips(ips)
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        windows_script("printer-check.ps1"), "-PrinterIP", ",".join(ips)],
                       capture_output=True, text=True, timeout=120, creationflags=0x08000000)       # CREATE_NO_WINDOW
    return (r.stdout + r.stderr).strip()


def windows_add_dymo(model, ip):
    if model not in ("550", "5XL"):
        raise ValueError("model must be 550 or 5XL")
    ip = check_ips([ip])[0]
    import ctypes
    args = (f'-NoProfile -ExecutionPolicy Bypass -File "{windows_script("add-dymo-printer.ps1")}" '
            f'-Model {model} -IP {ip} -Pause')
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", args, None, 1)
    if rc <= 32:
        raise RuntimeError("Windows didn't allow it (the admin prompt was declined?)")


# ------------------------------------------------------------------ printers found on the network (autoprint.py)
class QueueOps:
    """What autoprint needs from this PC: CUPS queues via lpstat/lpadmin (Fedora/Mac); Windows only reads."""
    _models = None

    def queue(self, kind):
        return queue_for(kind)

    def uri(self, q):
        if WINDOWS:
            return "windows:" + q if q else None
        r = subprocess.run(["lpstat", "-v", q], capture_output=True, text=True, timeout=10)
        m = re.search(r":\s*(\S+)\s*$", r.stdout.strip()) if r.returncode == 0 else None
        return m.group(1) if m else None

    def ppd(self, model):
        """The driver's model name for lpadmin -m (Fedora 'lw5xl.ppd', Mac 'Library/Printers/PPDs/…/lw5xl.ppd.gz')."""
        if self._models is None:
            r = subprocess.run(["lpinfo", "-m"], capture_output=True, text=True, timeout=30)
            QueueOps._models = [ln.split(" ", 1)[0] for ln in r.stdout.splitlines()]
        want = {"550T": "lw550t.ppd", "550": "lw550.ppd", "5XL": "lw5xl.ppd"}[model]
        for m in self._models:
            if m.rsplit("/", 1)[-1] in (want, want + ".gz"):
                return m
        raise RuntimeError("DYMO's driver isn't installed (" + ("DYMO Connect for Mac" if MAC else "tools/install-driver.sh") + ")")

    def add(self, kind, q, uri, model):
        lab = labels()[kind]
        desc = f"DYMO {autoprint.MODEL_NAME[model]} ({'inventory tags' if kind == 'tag' else 'shipping'})"
        self._lpadmin(["-p", q, "-E", "-v", uri, "-m", self.ppd(model), "-D", desc,
                       "-o", f"PageSize={lab['page']}", "-o", "printer-error-policy=abort-job"])

    def repoint(self, q, uri):
        self._lpadmin(["-p", q, "-v", uri])

    def _lpadmin(self, args):
        r = subprocess.run(["lpadmin", *args], capture_output=True, text=True, timeout=30)
        msg = "\n".join(ln for ln in (r.stderr + r.stdout).splitlines() if "deprecated" not in ln).strip()
        if r.returncode != 0:
            if "Forbidden" in msg or "not authorized" in msg.lower() or "password" in msg.lower():
                msg = "this user may not change printers — run tools/add-printers.sh in a Terminal"
            raise RuntimeError(msg or "lpadmin failed")

    def answers(self, ip, port):
        try:
            socket.create_connection((ip, port or dymo.PORT), timeout=1.5).close()
            return True
        except OSError:
            return False

    def busy(self, kind):
        if any(time.time() - t < 8 for t in RECENT.values()):          # LabelDesk just sent something
            return True
        if WINDOWS:
            return False
        try:
            return ipp.printer(queue_for(kind))["state"] == "printing"
        except (LookupError, OSError):
            return False


def _browse():
    """LabelDesk's own Bonjour scan (gives IPs → rolls) on Fedora; the Mac asks CUPS (macOS blocks the LaunchAgent's own
    scan); Windows asks the system's DNS-SD (winmdns.py) — its firewall would drop replies to LabelDesk's own scan."""
    if MAC:
        return dymo.browse_cups()
    if WINDOWS:                                    # the system's DNS-SD (its own firewall rules; no prompt for LabelDesk)
        import winmdns
        return winmdns.browse()
    found = dymo.browse()
    if not found and dymo.LAST.get("error") and not WINDOWS:
        return dymo.browse_cups()
    return found


AUTO = autoprint.Auto(QueueOps(), browse=_browse, can_manage=not WINDOWS)


def heal_once():
    """A queue that got paused (a printer that was off, a cable out) is resumed once its printer answers again — no more
    "press Resume". Fedora/Mac; Windows needs an admin for it, so there the bar still offers Resume. Off with
    "auto_resume": false."""
    if WINDOWS or not config().get("auto_resume", True):
        return
    for kind in ("tag", "ship"):
        q = queue_for(kind)
        try:
            p = ipp.printer(q)
        except (LookupError, OSError):
            continue
        if not (p["state"] == "stopped" or not p["accepting"]):
            continue
        ip, port = AUTO.host_for(kind)
        if ip and not AUTO.ops.answers(ip, port):
            continue                                                   # still off: leave it paused
        try:
            resume(kind)
            AUTO.event(f"The {'550 Turbo' if kind == 'tag' else '5XL'} was paused — it's answering again, so LabelDesk resumed it.")
        except RuntimeError as e:
            print("auto-resume:", e, flush=True)


def heal_loop(every=60):
    while True:
        time.sleep(every)
        try:
            heal_once()
        except Exception as e:                                         # noqa: BLE001 — never let it die
            print("auto-resume:", repr(e), flush=True)


def expected_stock(kind, cfg=None):
    return labels(cfg)[kind]["stock"].split()[0]


def roll_check(kind, want=None):
    """None, or why this label shouldn't print right now (wrong roll / no labels) — the page offers Print anyway."""
    if not config().get("auto_printers", True):
        return None
    try:
        r = AUTO.roll(kind)
    except Exception:                                              # noqa: BLE001 — the roll is a nicety, never block on it
        return None
    if not r:
        return None
    printer = "550 Turbo" if kind == "tag" else "5XL"
    if not r["canPrint"]:
        return f"the {printer} says {r['media']}"
    want = want or expected_stock(kind)
    if r["stock"] and r["stock"] != want:
        return (f"the {printer} has {r['name']} labels loaded, but LabelDesk is set to print {dymo.describe_roll(want) or want}"
                + (" — change it in Settings → Tag labels" if kind == "tag" else ""))
    return None


def printers():
    """Each configured queue: ok? plus the state in plain English (ipp.py / winprint), the roll in it, and what was
    found on the network."""
    out, auto = _printers(), bool(config().get("auto_printers", True))
    for kind in ("tag", "ship"):
        try:
            out[kind]["roll"] = AUTO.roll(kind) if auto else None
        except Exception:                                          # noqa: BLE001
            out[kind]["roll"] = None
        out[kind]["expect"] = expected_stock(kind)
    out["network"] = {"found": AUTO.found, "offers": AUTO.offers, "scannedAt": AUTO.at, "scanning": AUTO.scanning,
                      "auto": auto, "canManage": AUTO.can_manage,
                      "error": dymo.LAST.get("error")}
    return out


def use_printer(kind, k):
    """Settings → Printers on the network → Use for tags / shipping: point this kind's queue at that printer (k = its
    key: IP or CUPS URI, autoprint.key)."""
    if kind not in ("tag", "ship"):
        raise ValueError("kind must be tag or ship")
    p = next((p for p in AUTO.found if autoprint.key(p) == k), None)
    if not p:
        raise ValueError("that printer isn't on the network any more — Look again")
    if WINDOWS:
        if not p.get("ip"):
            raise ValueError("no address for that printer — add it in DYMO Connect")
        return windows_add_dymo("5XL" if p["model"] == "5XL" else "550", p["ip"])
    ops, q = AUTO.ops, queue_for(kind)
    if ops.uri(q) is None:
        ops.add(kind, q, autoprint.device_uri(p), p["model"])
    else:
        ops.repoint(q, autoprint.device_uri(p))
    AUTO.forget_roll(kind)
    AUTO.event(f"{'Tags' if kind == 'tag' else 'Shipping labels'} now print on the {autoprint.MODEL_NAME[p['model']]}{autoprint.where(p)}.")
    AUTO.offers = [o for o in AUTO.offers if autoprint.key(o) != k]


def _printers():
    out = {}
    if WINDOWS:
        for kind in ("tag", "ship"):
            name = queue_for(kind)
            if not name:
                out[kind] = {"queue": "", "ok": False, "paused": False,
                             "status": "not found on this PC — add it in DYMO Connect / Windows Settings → Printers"}
                continue
            try:
                p = winprint.printer(name)
            except RuntimeError as e:
                out[kind] = {"queue": name, "ok": False, "paused": False, "status": str(e)}
                continue
            bad = [r for r in p["reasons"] if r in WIN_PLAIN or r in ("not available",)]
            out[kind] = {"queue": name, "ok": not bad, "paused": "paused" in p["reasons"],
                         "status": win_plain({"reasons": bad}) if bad else "ready"}
        return out
    for kind in ("tag", "ship"):
        q = queue_for(kind)
        try:
            p = ipp.printer(q)
        except LookupError:
            out[kind] = {"queue": q, "ok": False, "paused": False,
                         "status": "not set up on this PC — run tools/add-printers.sh"}
            continue
        except OSError as e:
            out[kind] = {"queue": q, "ok": False, "paused": False, "status": f"CUPS isn't answering ({e})"}
            continue
        paused = p["state"] == "stopped" or not p["accepting"]
        errors = [r for r in p["reasons"] if r.endswith("-error") and r != "com.dymo.busy-error"]
        text = "paused on this PC — press Resume" if paused else (ipp.plain(errors) if errors else
                                                                   "printing" if p["state"] == "printing" else "ready")
        out[kind] = {"queue": q, "ok": not paused and not errors, "paused": paused, "status": text}
    return out


def cancel_job(hid):
    """The user caught a wrong label in time: cancel it while it's still waiting."""
    r = row(hid)
    if not r or not r["job"] or r["state"] in ("done", "failed"):
        raise ValueError("that label isn't waiting any more")
    if WINDOWS:
        winprint.cancel(r["queue"], r["job"])
    else:
        subprocess.run(["cancel", f"{r['queue']}-{r['job']}"], capture_output=True)
    update(hid, state="failed", message="cancelled")


def resume(kind):
    q = queue_for(kind)
    if WINDOWS:                                                  # resuming needs the Windows queue window (admin rights)
        subprocess.Popen(["rundll32", "printui.dll,PrintUIEntry", "/o", "/n", q])
        return
    for cmd in (["cupsenable", q], ["cupsaccept", q]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip() or f"{cmd[0]} failed")


def data_url(b):
    head, _, b64 = (b or "").partition(",")
    if not b64 or ";base64" not in head:
        raise ValueError("send a base64 data URL")
    return head[5:].split(";")[0], base64.b64decode(b64, validate=True)


def to_data_url(mime, raw):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


INBOX = None


def cw_creds():
    c = keys.load()
    if os.environ.get("LABELDESK_CW_BASE"):                       # tests / self-hosted ConnectWise
        c["base"] = os.environ["LABELDESK_CW_BASE"]
    return c


_cw_check = {}                                                  # creds → (time, working, problem); re-checked every 10 min


def cw_working(c):
    """Do these keys work right now? Only ever called with keys stored — without them LabelDesk never contacts
    ConnectWise (or anything else off this PC)."""
    key = tuple(c.get(k) for k in ("company", "public", "private", "client_id", "base"))
    hit = _cw_check.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1], hit[2]
    try:
        r = connectwise.test(c)
        ok = bool(r["ok"])
        problem = "" if ok else "; ".join(f"{x['what']}: {x['message']}" for x in r["checks"] if not x["ok"])
    except (connectwise.CWError, OSError, ValueError, KeyError) as e:
        ok, problem = False, str(e)
    _cw_check.clear()
    _cw_check[key] = (time.time(), ok, problem)
    return ok, problem


def cw_status():
    """ConnectWise is optional and off unless this PC has keys AND they work: {on, configured, working, problem, …}."""
    c = cw_creds()
    configured = all(c.get(k) for k in ("company", "public", "private", "client_id"))
    working, problem = cw_working(c) if configured else (False, "")
    return {"on": configured and working, "configured": configured, "working": working, "problem": problem,
            "company": c.get("company", ""), "clientId": c.get("client_id", ""),
            "publicKey": (c.get("public") or "")[:4] + "…" if c.get("public") else ""}


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = f"LabelDesk/{VERSION}"

    def log_message(self, fmt, *args):
        if "/api/job/" not in (args[0] if args else "") and "/api/inbox" not in (args[0] if args else ""):
            print(f"{self.address_string()} {fmt % args}", flush=True)

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, data, kind, cache=False):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        # wasm-unsafe-eval: the ZXing barcode reader is WebAssembly; pdf.js runs in a same-origin worker
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; img-src 'self' "
                         "data: blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def local_host(self):
        """Only http://127.0.0.1:<port> / localhost:<port>. A web page whose own domain is re-pointed at 127.0.0.1
        (DNS rebinding) would otherwise count as "same origin" and could read the history or print."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host in ("127.0.0.1", "localhost", "::1"):
            return True
        self.send_json({"error": "LabelDesk only answers on this PC (http://127.0.0.1:8792)"}, 403)
        return False

    def do_GET(self):
        if not self.local_host():
            return
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, urllib.parse.parse_qs(u.query)
        try:
            if path == "/api/config":
                cfg = config()
                return self.send_json({"version": VERSION, "labels": labels(cfg), "tagStocks": TAG_STOCKS,
                                       "tagLabel": labels(cfg)["tag"]["stock"].split()[0], "flipTag": cfg["flip_tag"], "tagOffsetMm": float(cfg.get("tag_offset_mm") or 0),
                                       "barcodeCheck": barcode.available(), "started": STARTED,
                                       "autoShip": bool(cfg.get("auto_ship")),
                                       "tagBarcode": cfg.get("tag_barcode") if cfg.get("tag_barcode") in ("code128", "code39") else "code128", "platform": "windows" if WINDOWS else "mac" if MAC else "linux"})
            if path == "/api/printers":
                return self.send_json(printers())
            if path == "/api/printers/events":               # ?after=<id>: what LabelDesk did by itself
                return self.send_json({"events": AUTO.since(int((q.get("after") or ["0"])[0]))})
            if path == "/api/update":
                return self.send_json(check_update())
            if path == "/api/stocks":                        # the designer's label list
                return self.send_json({"stocks": list(STOCKS.values())})
            if path == "/api/templates/shared":              # the shop's templates (templates/*.json in the repo)
                return self.send_json({"templates": shared_templates()})
            if path == "/api/versions":                      # Settings → Version
                return self.send_json(versions_info())
            if path == "/api/update/log":
                try:
                    with open(update_log(), encoding="utf-8", errors="replace") as f:
                        return self.send_json({"log": f.read()[-4000:]})
                except OSError:
                    return self.send_json({"log": ""})
            if path == "/api/logo":
                try:
                    with open(logo_path(), "rb") as f:
                        raw = f.read()
                except OSError:
                    return self.send_json({"error": "no logo on this PC"}, 404)
                return self.send_bytes(raw, "image/jpeg" if raw[:2] == b"\xff\xd8" else "image/png")
            if path == "/api/history.csv":
                f = {k: (q.get(k) or [""])[0] for k in ("q", "kind", "since", "until")}
                body = history_csv(**f).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="labeldesk-history-{datetime.now():%Y-%m-%d}.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/device":                        # ?serial= — been here before?
                return self.send_json(device_info((q.get("serial") or [""])[0]))
            if m := re.fullmatch(r"/api/ticket/(\d{1,10})", path):  # History → Scan a tag
                return self.send_json(ticket_info(m.group(1)))
            if path == "/api/history":
                f = {k: (q.get(k) or [""])[0] for k in ("q", "kind", "since", "until")}
                items = history(limit=min(500, int((q.get("limit") or ["60"])[0])), before=int((q.get("before") or ["0"])[0]), **f)
                for r in [r for r in items if r["state"] == "sent" and r["job"]][:10]:   # nobody watched it finish
                    try:
                        r.update(state=job_status(r["id"])["state"])
                    except Exception:                          # printer / CUPS unreachable: leave it as sent
                        pass
                    if r["state"] == "waiting":
                        r["state"] = "sent"
                return self.send_json({"items": items})
            if path == "/api/customers":
                return self.send_json({"customers": customers()})
            if path == "/api/cw/status":
                return self.send_json(cw_status())
            if m := re.fullmatch(r"/api/cw/ticket/(\d{1,10})", path):
                try:
                    return self.send_json(connectwise.ticket(cw_creds(), m.group(1)))
                except LookupError:
                    return self.send_json({"error": f"no ticket #{m.group(1)} in ConnectWise"}, 404)
            if path == "/api/cw/configurations":
                return self.send_json({"items": connectwise.configurations(
                    cw_creds(), int((q.get("company") or ["0"])[0]), (q.get("ticket") or [None])[0])})
            if m := re.fullmatch(r"/api/job/(\d+)", path):
                return self.send_json(job_status(int(m.group(1))))
            if m := re.fullmatch(r"/api/history/(\d+)/image", path):
                r = row(int(m.group(1)))
                if not r or not r.get("image") or not os.path.isfile(r["image"]):
                    return self.send_json({"error": "no image kept for that print"}, 404)
                with open(r["image"], "rb") as f:
                    return self.send_bytes(f.read(), "image/png")
            if path == "/api/inbox":
                return self.send_json({"items": INBOX.since(int((q.get("after") or ["0"])[0])) if INBOX else []})
            if m := re.fullmatch(r"/api/inbox/(\d+)", path):
                item = INBOX and INBOX.get(int(m.group(1)))
                if not item or not os.path.isfile(item["path"]):
                    return self.send_json({"error": "that file is gone"}, 404)
                if item["path"].lower().endswith(".pdf"):
                    with open(item["path"], "rb") as f:             # the browser renders it (pdf.js) — same on both OSes
                        return self.send_json({"name": item["name"], "pdf": to_data_url("application/pdf", f.read()),
                                               "verify": item.get("verify", False)})
                with open(item["path"], "rb") as f:
                    raw = f.read()
                return self.send_json({"name": item["name"],
                                       "png": to_data_url(mimetypes.guess_type(item["path"])[0] or "image/png", raw)})
        except (KeyError, ValueError) as e:
            return self.send_json({"error": str(e).strip("'")}, 400)
        except connectwise.CWError as e:
            return self.send_json({"error": str(e)}, 502)
        rel = "index.html" if path in ("", "/") else urllib.parse.unquote(path).lstrip("/")
        full = os.path.realpath(os.path.join(WEB, rel))
        if not full.startswith(WEB + os.sep) or not os.path.isfile(full):
            return self.send_json({"error": "not found"}, 404)
        kind = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
                ".svg": "image/svg+xml", ".png": "image/png", ".wasm": "application/wasm",
                ".txt": "text/plain"}.get(os.path.splitext(full)[1], "application/octet-stream")
        with open(full, "rb") as f:
            self.send_bytes(f.read(), kind, cache=os.sep + "vendor" + os.sep in full)

    def do_POST(self):
        if not self.local_host():
            return
        path = urllib.parse.urlparse(self.path).path
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host"):
            return self.send_json({"error": "cross-site request refused"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self.send_json({"error": "too large"}, 413)
        try:
            b = json.loads(self.rfile.read(n) or b"{}")
            if path == "/api/print":                       # {kind, png, copies, fields, force}
                kind = b.get("kind")
                if kind not in LABELS:
                    raise ValueError("kind must be tag or ship")
                media, png = data_url(b.get("png"))
                if media != "image/png":
                    raise ValueError("expected a PNG")
                copies = max(1, min(99, int(b.get("copies") or 1)))
                fields = b.get("fields") if isinstance(b.get("fields"), dict) else {}
                gray = None
                if b.get("gray"):                              # Windows + Mac: {w, h, data: base64 of w*h grey bytes}
                    g = b["gray"]
                    raw = base64.b64decode(g["data"], validate=True)
                    if len(raw) != int(g["w"]) * int(g["h"]):
                        raise ValueError("grey image size mismatch")
                    gray = (int(g["w"]), int(g["h"]), raw)
                stock = b.get("stock") or None
                if stock is not None and stock not in STOCKS:
                    raise ValueError("unknown label")
                res, code = print_label(kind, png, copies, fields, force=bool(b.get("force")), gray=gray,
                                        client_check=b.get("check") if isinstance(b.get("check"), dict) else None, stock=stock)
                return self.send_json(res, code)
            if m := re.fullmatch(r"/api/job/(\d+)/cancel", path):
                cancel_job(int(m.group(1)))
                return self.send_json({"ok": True})
            if m := re.fullmatch(r"/api/printers/(tag|ship)/resume", path):
                resume(m.group(1))
                return self.send_json({"ok": True})
            if path == "/api/cw/settings":                 # keys typed into Settings → the OS keyring (keys.py)
                _cw_check.clear()
                cur = keys.load()
                new = {k: (b.get(k) or "").strip() or cur.get(k, "") for k in ("company", "public", "private", "client_id")}
                where = keys.save(new)                     # a blank private key keeps the stored one
                return self.send_json(cw_status() | {"savedIn": where})
            if path == "/api/cw/test":
                _cw_check.clear()
                return self.send_json(connectwise.test(cw_creds()))
            if path == "/api/cw/clear":
                _cw_check.clear()
                keys.clear()
                return self.send_json(cw_status())
            if m := re.fullmatch(r"/api/ticket/(\d{1,10})/collected", path):   # {collected: bool} — this PC's record only
                set_collected(m.group(1), bool(b.get("collected", True)))
                return self.send_json(ticket_info(m.group(1)))
            if path == "/api/templates/share":               # {template} → templates/<name>.json in this checkout
                return self.send_json({"ok": True, "path": share_template(b.get("template"))})
            if path == "/api/sheet":                         # Batch → Open spreadsheet: {name, data: base64} → columns + rows
                return self.send_json(sheet.read(str(b.get("name") or ""), base64.b64decode(b.get("data") or "", validate=True)))
            if path == "/api/settings/auto-ship":            # Settings → Shipping labels print by themselves: {on}
                save_config(auto_ship=bool(b.get("on")))
                return self.send_json({"ok": True})
            if path == "/api/settings/tag-barcode":          # Settings → Tag barcode: {symbology: code128 | code39}
                sym = str(b.get("symbology") or "")
                if sym not in ("code128", "code39"):
                    raise ValueError("tag barcode must be code128 or code39")
                save_config(tag_barcode=sym)
                return self.send_json({"ok": True})
            if path == "/api/settings/tag-label":            # Settings → Tag labels: {label: "30252" | "30321"}
                stock = str(b.get("label") or "")
                if stock not in TAG_STOCKS:
                    raise ValueError("label must be one of " + ", ".join(TAG_STOCKS))
                save_config(tag_label=stock)
                return self.send_json({"ok": True, "labels": labels()})
            if path == "/api/logo":                          # Settings → Tag logo: {png: data URL}
                save_logo(b.get("png") or "")
                return self.send_json({"ok": True})
            if path == "/api/logo/clear":
                try:
                    os.remove(logo_path())
                except FileNotFoundError:
                    pass
                return self.send_json({"ok": True})
            if path == "/api/version/use":                   # {version: "0.8.1" | "newest", everyone: bool}
                use_version(b.get("version"), bool(b.get("everyone")))
                _update.update(at=0, result=None)
                return self.send_json({"ok": True})
            if path == "/api/printers/scan":                 # Settings → Look again
                AUTO.scan()
                return self.send_json({"ok": True})
            if path == "/api/printers/use":                  # {kind, ip}: use this printer found on the network
                use_printer(str(b.get("kind") or ""), str(b.get("key") or b.get("ip") or ""))
                return self.send_json({"ok": True})
            if path == "/api/update/run":                    # Fedora: Update now (no local changes only)
                run_update_now()
                _update.update(at=0, result=None)
                return self.send_json({"ok": True, "log": update_log()})
            if path == "/api/update/install":                # Windows: download + install the new MSI
                install_windows_update(str(b.get("version") or ""))
                return self.send_json({"ok": True})
            if path == "/api/windows/printer-check":         # read-only; output shown in Settings
                if not WINDOWS:
                    raise ValueError("Windows only (on Fedora: tools/doctor.sh)")
                return self.send_json({"output": windows_printer_check(b.get("ips") or [])})
            if path == "/api/windows/add-dymo":              # {model, ip}: elevated add-dymo-printer.ps1 (UAC prompt)
                if not WINDOWS:
                    raise ValueError("on Fedora the printers come from tools/add-printers.sh")
                windows_add_dymo(str(b.get("model") or ""), str(b.get("ip") or ""))
                return self.send_json({"ok": True})
            if path == "/api/windows/add-printer":         # Settings → "Add the Shipping Label printer" (UAC prompt)
                if not WINDOWS:
                    raise ValueError("on Fedora the printer comes from tools/add-printers.sh")
                import ctypes
                script = os.path.join(os.path.dirname(HERE), "add-shipping-printer.ps1")
                args = f'-NoProfile -ExecutionPolicy Bypass -File "{script}" -Inbox "{SPOOL}"'
                rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", args, None, 0)
                if rc <= 32:
                    raise RuntimeError("Windows didn't allow it (the admin prompt was declined?)")
                return self.send_json({"ok": True})
            return self.send_json({"error": "not found"}, 404)
        except (ValueError, KeyError) as e:
            return self.send_json({"error": str(e).strip("'")}, 400)
        except (RuntimeError, connectwise.CWError) as e:
            return self.send_json({"error": str(e)}, 502)


def main():
    global INBOX
    cfg = config()
    dl = os.environ.get("LABELDESK_DOWNLOADS") or downloads_dir()
    dirs = ([] if MAC else [(SPOOL, True)]) + ([(dl, False)] if cfg["watch_downloads"] else [])   # Mac: no print-dialog printer
    INBOX = Inbox(dirs)
    threading.Thread(target=INBOX.run, daemon=True).start()
    if cfg.get("auto_printers", True):
        threading.Thread(target=AUTO.run, daemon=True).start()
    threading.Thread(target=heal_loop, daemon=True).start()
    try:
        migrate_logo()
    except OSError as e:
        print(f"couldn't move the old tag logo: {e}", flush=True)
    print(f"LabelDesk {VERSION} on http://{cfg['bind']}:{cfg['port']}  tag→{queue_for('tag')}  ship→{queue_for('ship')}  "
          f"watching {', '.join(d for d, _ in dirs)}  zbar {'on' if barcode.available() else 'off (the browser checks barcodes)'}",
          flush=True)
    srv = ThreadingHTTPServer((cfg["bind"], cfg["port"]), Handler)
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == "__main__":
    main()
