"""Shipping labels arriving on their own: new carrier PDFs in Downloads, and jobs printed to the "Shipping Label
(LabelDesk)" printer from any app's print dialog (tools/add-printers.sh sets it up; its CUPS backend drops the PDF
into SPOOL). The app polls /api/inbox and opens the newest one on the Shipping tab, ready to print.

Downloads: only files that appear after LabelDesk started, only PDFs/images, and only ones that look like a shipping
label (a PDF's text mentions UPS / FedEx / USPS / tracking; images are offered only from the print spool).
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time

WINDOWS = sys.platform == "win32"
# the print-dialog printer drops its jobs here (Fedora: CUPS backend; Windows: a "Print to PDF" printer's file port)
SPOOL = (os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LabelDesk", "inbox") if WINDOWS
         else "/var/spool/labeldesk")
LABEL_WORDS = re.compile(r"\b(UPS|FedEx|USPS|TRACKING|TRK#|1Z[0-9A-Z]{16}|Ship Manager|Print Your Label)", re.I)


def downloads_dir():
    if WINDOWS:                                                  # the real Downloads folder, even if it was moved
        try:
            import ctypes
            from ctypes import wintypes
            guid = (ctypes.c_byte * 16).from_buffer_copy(bytes.fromhex("90e24d373f126545916439c4925e467b"))  # FOLDERID_Downloads
            path = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path)) == 0:
                d = path.value
                ctypes.windll.ole32.CoTaskMemFree(path)
                return d
        except (OSError, AttributeError):
            pass
        return os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Downloads")
    try:
        d = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        if d and os.path.isdir(d):
            return d
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.expanduser("~/Downloads")


def looks_like_label(path):
    """True / False — or None when this PC can't read PDF text (Windows): then the browser checks it with pdf.js."""
    if path.lower().endswith(".pdf") and not shutil.which("pdftotext"):
        return None
    if path.lower().endswith(".pdf"):
        try:
            text = subprocess.run(["pdftotext", "-l", "2", path, "-"], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return bool(LABEL_WORDS.search(text))
    return False


class Inbox:
    def __init__(self, dirs, interval=2.0):
        self.dirs, self.interval = dirs, interval
        self.items, self.next_id, self.lock = [], 1, threading.Lock()
        self.seen = {}                                          # path → arrival time last handled (a rewritten file counts again:
                                                                # Windows' Print-to-PDF port writes the same file each time)
        self.started = time.time()

    def scan(self):
        for d, trusted in self.dirs:
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for n in names:
                p = os.path.join(d, n)
                if n.startswith(".") or n.endswith((".part", ".crdownload", ".tmp")) or not os.path.isfile(p):
                    continue
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                # when it ARRIVED: Firefox stamps a download with the server's date, so mtime alone can be months old;
                # ctime (Linux: the download's rename; Windows: creation) catches that
                arrived = max(st.st_mtime, st.st_ctime, getattr(st, "st_birthtime", 0))
                if self.seen.get(p) == arrived or arrived < self.started - 5:
                    self.seen.setdefault(p, arrived)
                    continue
                if time.time() - arrived < 1.5:                 # still being written — look again next round
                    continue
                self.seen[p] = arrived
                ext = n.lower().rsplit(".", 1)[-1]
                if ext not in ("pdf", "png", "jpg", "jpeg", "gif", "webp"):
                    continue
                verdict = True if trusted else looks_like_label(p)
                if verdict is False:
                    continue
                with self.lock:
                    self.items.append({"id": self.next_id, "path": p, "name": n, "at": time.time(), "verify": verdict is None,
                                       "source": "print dialog" if trusted else "Downloads"})
                    self.next_id += 1
                    self.items = self.items[-50:]

    def run(self):
        while True:
            try:
                self.scan()
            except Exception as e:                              # never let the watcher die
                print("inbox:", repr(e), flush=True)
            time.sleep(self.interval)

    def since(self, after):
        with self.lock:
            return [{k: v for k, v in i.items() if k != "path"} for i in self.items if i["id"] > after]

    def get(self, item_id):
        with self.lock:
            return next((i for i in self.items if i["id"] == item_id), None)
