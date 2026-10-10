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

import barcode
import connectwise
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
# after each print the app asks GitHub for the newest VERSION (a plain GET of one small file; no label content, no IDs)
REPO = "cpkrepo/LabelDesk_Public"
UPDATE_URL = f"https://raw.githubusercontent.com/{REPO}/main/VERSION"
RELEASES_URL = f"https://github.com/{REPO}/releases"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/tags/v{{version}}"
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
         "tag_label": DEFAULT_TAG_STOCK}
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
COLUMNS = {"state": "TEXT", "message": "TEXT", "image": "TEXT", "tracking": "TEXT"}


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


def history(limit=80):
    c = db()
    rows = [dict(r) | {"fields": json.loads(r["fields"])} for r in
            c.execute("SELECT * FROM printed ORDER BY id DESC LIMIT ?", (limit,))]
    c.close()
    return rows


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


def submit(kind, png_bytes, copies, gray=None):
    """Hand one label to the printer. Fedora: the PNG through CUPS (lp). Windows: the 8-bit grey image through DYMO's
    Windows driver (winprint). → (queue/printer, job id)."""
    if WINDOWS:
        printer = queue_for(kind)
        if not printer:
            raise RuntimeError(f"no DYMO {'550 Turbo' if kind == 'tag' else '5XL'} printer on this PC — add it in DYMO Connect "
                               "or Windows Settings → Printers")
        if not gray:
            raise ValueError("the Windows version needs the label as grey pixels (update LabelDesk)")
        lab = labels()[kind]
        job, _paper = winprint.submit(printer, kind, gray, copies, f"LabelDesk {lab['name']}",
                                      paper=(lab["stock"].split()[0],) if kind == "tag" else None)
        return printer, job
    if MAC and gray:
        return lp(kind, label_pdf(labels()[kind], *gray), copies, ".pdf")
    return lp(kind, png_bytes, copies)


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


def lp(kind, data, copies, suffix=".png"):
    """Send one label (PNG, or the exact-size PDF from label_pdf) to its queue at exactly 300 dpi on the right page
    size. → (queue, job number)."""
    queue = queue_for(kind)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        lab = labels()[kind]
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


def print_label(kind, png, copies, fields, force=False, gray=None, client_check=None):
    digest = hashlib.sha1(png + f"{kind}:{copies}".encode()).hexdigest()
    if not force and time.time() - RECENT.get(digest, 0) < 3:
        return {"duplicate": True, "error": "that label was just sent — press Print again to print another"}, 409
    check = None
    if kind == "ship":
        # zbar here (Fedora) double-checks; without it (Windows) the browser's ZXing check stands
        check = barcode.check(png) if barcode.available() else (client_check or {"ok": True, "tracking": None})
        if not check.get("ok") and not force:
            return {"needsForce": True, "check": check, "error": check.get("message", "no barcode could be read")}, 422
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
        queue, job = submit(kind, png, copies, gray)
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
    if not res["enabled"]:
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
    os.makedirs(DATA, exist_ok=True)
    cmd = f"cd {shlex_quote(ROOT)} && tools/update.sh > {shlex_quote(update_log())} 2>&1"
    if MAC:                                                      # own session: survives launchd restarting LabelDesk
        subprocess.Popen(["/bin/bash", "-c", cmd], start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if not shutil.which("systemd-run"):
        raise ValueError("systemd-run isn't available — run tools/update.sh in a Terminal")
    subprocess.run(["systemd-run", "--user", "--collect", "--quiet", f"--unit=labeldesk-update-{int(time.time())}",
                    "/bin/bash", "-c", cmd], check=True, capture_output=True, timeout=15)


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
    """Windows "Install update": the MSI for `version` from the GitHub release, checked against the release's
    .sha256, installed per user (no admin) by a helper that waits for this server to exit, then starts it again."""
    if not WINDOWS:
        raise ValueError("on Fedora use Update now / tools/update.sh")
    if not version_tuple(version) or version_tuple(version) <= version_tuple(VERSION):
        raise ValueError("no newer version to install")
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
    ps = (f"Wait-Process -Id {os.getpid()} -Timeout 60 -ErrorAction SilentlyContinue; "
          f"$p = Start-Process msiexec.exe -ArgumentList '/i','\"{msi_path}\"','/qb','/l*v','\"{log}\"' -Wait -PassThru; "
          f"Start-Process '{pythonw}' -ArgumentList '\"{server}\"'; exit $p.ExitCode")
    script = os.path.join(work, "install-update.ps1")
    with open(script, "w", encoding="utf-8") as f:
        f.write(ps + "\n")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script],
                     creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
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


def printers():
    """Each configured queue: ok? plus the state in plain English (ipp.py / winprint)."""
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
                                       "barcodeCheck": barcode.available(), "platform": "windows" if WINDOWS else "mac" if MAC else "linux"})
            if path == "/api/printers":
                return self.send_json(printers())
            if path == "/api/update":
                return self.send_json(check_update())
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
            if path == "/api/history":
                items = history()
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
                res, code = print_label(kind, png, copies, fields, force=bool(b.get("force")), gray=gray,
                                        client_check=b.get("check") if isinstance(b.get("check"), dict) else None)
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
