"""Windows printing for LabelDesk — through DYMO's own Windows driver (installed with DYMO Connect). ctypes only.

  submit(printer, kind, gray, copies) → job id      the label as 8-bit grayscale (w, h, bytes) at 300 dpi, drawn at its
                                                    exact physical size, centred, on DYMO's paper for that label kind
  job(printer, job_id) → {state, message}           state: waiting | done | failed (job left the queue without error = done)
  printer(printer) → {state, reasons, message, accepting}
  find() → {"tag": name, "ship": name}              the DYMO printers installed on this PC (550 Turbo / 5XL)

Paper is chosen by DYMO's own paper names (DeviceCapabilities DC_PAPERNAMES): the tag stock's number ("30252",
"30321") for tags,
"1744907 4 in x 6 in" / "4 in x 6 in" for shipping. Nothing here runs on Linux — app.py picks cups or this module.
"""
import ctypes
import sys

if sys.platform == "win32":
    from ctypes import wintypes
    winspool, gdi32 = ctypes.WinDLL("winspool.drv", use_last_error=True), ctypes.WinDLL("gdi32", use_last_error=True)
    # handles are pointers: without these, ctypes would truncate an HDC to 32 bits on 64-bit Windows
    HDC = ctypes.c_void_p
    gdi32.CreateDCW.restype = HDC
    gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
    for fn in ("StartPage", "EndPage", "EndDoc", "DeleteDC"):
        getattr(gdi32, fn).argtypes = [HDC]
    gdi32.StartDocW.argtypes = [HDC, ctypes.c_void_p]
    gdi32.GetDeviceCaps.argtypes = [HDC, ctypes.c_int]
    gdi32.SetStretchBltMode.argtypes = [HDC, ctypes.c_int]
    gdi32.StretchDIBits.argtypes = [HDC] + [ctypes.c_int] * 8 + [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.DWORD]

PAPER = {"tag": ("30252",), "ship": ("1744907", "4 in x 6 in", "4in x 6in", "4 x 6")}
DPI = 300
# GetDeviceCaps indexes
HORZRES, VERTRES, LOGPIXELSX, LOGPIXELSY = 8, 10, 88, 90
PHYSICALWIDTH, PHYSICALHEIGHT, PHYSICALOFFSETX, PHYSICALOFFSETY = 110, 111, 112, 113
# job / printer status bits (winspool.h)
JOB_STATUS = {0x2: "error", 0x4: "deleting", 0x10: "printing", 0x20: "offline", 0x40: "paper out", 0x80: "printed",
              0x100: "deleted", 0x200: "blocked", 0x400: "needs attention", 0x1000: "complete", 0x1: "paused"}
PRINTER_STATUS = {0x1: "paused", 0x2: "error", 0x10: "paper jam", 0x20: "paper out", 0x80: "offline", 0x400: "busy",
                  0x100000: "needs attention", 0x400000: "door open", 0x200: "not available", 0x80000: "manual feed"}


# the Windows errors a shop PC actually hits, in plain words (the number stays, for whoever looks it up)
WIN_ERRORS = {1722: "Windows' print service isn't running — restart the PC (or start \"Print Spooler\" in Services)",
              1801: "that printer isn't installed on this PC any more — add it again in DYMO Connect",
              1797: "the DYMO driver is missing — reinstall DYMO Connect",
              5: "Windows refused (access denied) — ask whoever manages this PC",
              1804: "the DYMO driver refused the label — reinstall DYMO Connect"}


def _check(ok, what):
    if not ok:
        code = ctypes.get_last_error()
        plain = WIN_ERRORS.get(code)
        raise RuntimeError(f"{what} failed: {plain} (Windows error {code})" if plain else
                           f"{what} failed (Windows error {code})")


class DOCINFOW(ctypes.Structure if sys.platform == "win32" else object):
    if sys.platform == "win32":
        _fields_ = [("cbSize", ctypes.c_int), ("lpszDocName", wintypes.LPCWSTR), ("lpszOutput", wintypes.LPCWSTR),
                    ("lpszDatatype", wintypes.LPCWSTR), ("fwType", wintypes.DWORD)]


class PRINTER_INFO_2(ctypes.Structure if sys.platform == "win32" else object):
    if sys.platform == "win32":
        _fields_ = [(f, wintypes.LPWSTR) for f in ("pServerName", "pPrinterName", "pShareName", "pPortName",
                                                    "pDriverName", "pComment", "pLocation")] + \
                   [("pDevMode", ctypes.c_void_p)] + \
                   [(f, wintypes.LPWSTR) for f in ("pSepFile", "pPrintProcessor", "pDatatype", "pParameters")] + \
                   [("pSecurityDescriptor", ctypes.c_void_p)] + \
                   [(f, wintypes.DWORD) for f in ("Attributes", "Priority", "DefaultPriority", "StartTime",
                                                   "UntilTime", "Status", "cJobs", "AveragePPM")]


def find():
    """Installed DYMO 550 Turbo / 5XL printers (EnumPrinters: local + network connections), by printer name, else by
    driver name — users rename them ("Asset Tags", "Shipping Labels"); the driver keeps saying "LabelWriter 5XL"."""
    PRINTER_ENUM_LOCAL, PRINTER_ENUM_CONNECTIONS = 0x2, 0x4
    need, got = wintypes.DWORD(), wintypes.DWORD()
    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    winspool.EnumPrintersW(flags, None, 2, None, 0, ctypes.byref(need), ctypes.byref(got))
    buf = ctypes.create_string_buffer(need.value)
    _check(winspool.EnumPrintersW(flags, None, 2, buf, need, ctypes.byref(need), ctypes.byref(got)), "EnumPrinters")
    printers = [(p.pPrinterName, (p.pDriverName or "").lower(), p.Status, p.Attributes)
                for p in ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_2 * got.value)).contents]
    return pick_printers(printers, answers)


def answers(name):
    """Does the printer's TCP/IP port address answer? None = not a TCP/IP port (can't tell)."""
    import socket
    try:
        host, port = port_address(name)
    except (RuntimeError, OSError):
        return None
    if not host:
        return None
    try:
        socket.create_connection((host, port), timeout=1).close()
        return True
    except OSError:
        return False


def pick_printers(printers, answers=None):
    """[(name, driver lowercased, status, attributes)] → {"tag", "ship", "all"}. A name match beats a driver match; among
    several (a re-added printer leaves "… (Copy 1)" beside the old one, often pointing at the printer's OLD address and
    not marked offline by Windows) one that answers on the network wins, then one Windows doesn't call offline, then
    one that isn't a copy. answers(name) → True/False/None is only asked when there's a choice."""
    PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x400

    def rank(p, reach):
        name, _, status, attrs = p
        return (reach.get(name) is False,
                bool(status & (0x80 | 0x2 | 0x200) or attrs & PRINTER_ATTRIBUTE_WORK_OFFLINE),   # offline/error/n.a.
                "(copy" in name.lower())

    def pick(*words):
        for group in ([p for p in printers if all(w in p[0].lower() for w in words)],
                      [p for p in printers if "dymo" in p[1] and all(w in p[1] for w in words)]):
            if group:
                reach = {p[0]: answers(p[0]) for p in group} if answers and len(group) > 1 else {}
                return min(group, key=lambda p: rank(p, reach))[0]   # min is stable: first listed wins a tie
        return None

    return {"tag": pick("550", "turbo") or pick("550"), "ship": pick("5xl"), "all": [p[0] for p in printers]}


def _devmode(printer, kind, copies, words=None):
    """The driver's DEVMODE with DYMO's paper for `kind`, portrait, `copies`. → (buffer, paper name)."""
    h = wintypes.HANDLE()
    _check(winspool.OpenPrinterW(printer, ctypes.byref(h), None), f"opening printer {printer!r}")
    try:
        size = winspool.DocumentPropertiesW(None, h, printer, None, None, 0)
        _check(size > 0, "DocumentProperties")
        dm = ctypes.create_string_buffer(size)
        _check(winspool.DocumentPropertiesW(None, h, printer, dm, None, 2) >= 0, "DocumentProperties")   # DM_OUT_BUFFER
        # papers the driver offers: DC_PAPERNAMES (16) = 64-wchar names, DC_PAPERS (2) = WORD ids
        n = winspool.DeviceCapabilitiesW(printer, None, 16, None, None)
        names = ctypes.create_unicode_buffer(64 * max(n, 1))
        winspool.DeviceCapabilitiesW(printer, None, 16, names, None)
        ids = (wintypes.WORD * max(n, 1))()
        winspool.DeviceCapabilitiesW(printer, None, 2, ids, None)
        papers = [(names[i * 64:(i + 1) * 64].split("\0", 1)[0], ids[i]) for i in range(n)]
        words = words or PAPER[kind]
        want = next(((nm, pid) for word in words for nm, pid in papers if word.lower() in nm.lower()), None)
        if not want:
            raise RuntimeError(f"{printer} has no {words[0]} paper size — is it the right printer?")
        # DEVMODEW: dmDeviceName WCHAR[32] (64 bytes) + 4 WORDs → dmFields @72; then dmOrientation @76,
        # dmPaperSize @78, dmPaperLength @80, dmPaperWidth @82, dmScale @84, dmCopies @86
        DM_ORIENTATION, DM_PAPERSIZE, DM_COPIES = 0x1, 0x2, 0x100
        fields = int.from_bytes(dm.raw[72:76], "little") | DM_ORIENTATION | DM_PAPERSIZE | DM_COPIES
        ctypes.memmove(ctypes.addressof(dm) + 72, fields.to_bytes(4, "little"), 4)
        ctypes.memmove(ctypes.addressof(dm) + 76, (1).to_bytes(2, "little"), 2)                  # DMORIENT_PORTRAIT
        ctypes.memmove(ctypes.addressof(dm) + 78, int(want[1]).to_bytes(2, "little"), 2)
        ctypes.memmove(ctypes.addressof(dm) + 86, int(copies).to_bytes(2, "little"), 2)
        _check(winspool.DocumentPropertiesW(None, h, printer, dm, dm, 2 | 8) >= 0, "DocumentProperties (apply)")  # OUT|IN
        return dm, want[0]
    finally:
        winspool.ClosePrinter(h)


def submit(printer, kind, gray, copies=1, title="LabelDesk", paper=None):
    """Print `copies` labels as one job. gray = (width, height, bytes: one 0-255 value per pixel, rows top-down) at
    300 dpi. Each copy is its own page (the driver's DEVMODE copies stays 1): drivers may ignore dmCopies — DYMO's CUPS
    driver ignores its equivalent — and a page per label always prints that many."""
    w, h, pixels = gray
    dm, paper = _devmode(printer, kind, 1, paper)
    hdc = gdi32.CreateDCW("WINSPOOL", printer, None, dm)
    _check(hdc, f"opening {printer}")
    try:
        di = DOCINFOW(ctypes.sizeof(DOCINFOW), title, None, None, 0)
        job = gdi32.StartDocW(hdc, ctypes.byref(di))
        _check(job > 0, "StartDoc")
        dpx, dpy = gdi32.GetDeviceCaps(hdc, LOGPIXELSX), gdi32.GetDeviceCaps(hdc, LOGPIXELSY)
        pw, ph = gdi32.GetDeviceCaps(hdc, PHYSICALWIDTH), gdi32.GetDeviceCaps(hdc, PHYSICALHEIGHT)
        ox, oy = gdi32.GetDeviceCaps(hdc, PHYSICALOFFSETX), gdi32.GetDeviceCaps(hdc, PHYSICALOFFSETY)
        dw, dh = round(w * dpx / DPI), round(h * dpy / DPI)                  # exact physical size…
        x, y = (pw - dw) // 2 - ox, (ph - dh) // 2 - oy                      # …centred on the label
        # 8-bit DIB, grey palette, rows padded to 4 bytes, top-down (negative height)
        stride = (w + 3) & ~3
        bits = pixels if stride == w else b"".join(pixels[r * w:(r + 1) * w] + b"\xff" * (stride - w) for r in range(h))

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD), ("palette", wintypes.DWORD * 256)]

        bmi = BITMAPINFO(40, w, -h, 1, 8, 0, len(bits), 11811, 11811, 256, 256)
        for i in range(256):
            bmi.palette[i] = (i << 16) | (i << 8) | i
        for _ in range(max(1, int(copies))):
            _check(gdi32.StartPage(hdc) > 0, "StartPage")
            gdi32.SetStretchBltMode(hdc, 4)                                  # HALFTONE (reset by StartPage)
            _check(gdi32.StretchDIBits(hdc, x, y, dw, dh, 0, 0, w, h, bits, ctypes.byref(bmi), 0, 0x00CC0020) != 0,
                   "StretchDIBits")                                          # DIB_RGB_COLORS, SRCCOPY
            _check(gdi32.EndPage(hdc) > 0, "EndPage")
        _check(gdi32.EndDoc(hdc) > 0, "EndDoc")
        return str(job), paper
    finally:
        gdi32.DeleteDC(hdc)


def queued(printer):
    """How many jobs are in the printer's Windows queue (PRINTER_INFO_2.cJobs)."""
    h = _open(printer)
    try:
        need = wintypes.DWORD()
        winspool.GetPrinterW(h, 2, None, 0, ctypes.byref(need))
        buf = ctypes.create_string_buffer(need.value)
        _check(winspool.GetPrinterW(h, 2, buf, need, ctypes.byref(need)), "GetPrinter")
        return ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_2)).contents.cJobs
    finally:
        winspool.ClosePrinter(h)


def port_address(printer):
    """Where a printer's Windows port sends its jobs → (host, port), or (None, None) when it isn't a Standard TCP/IP port
    (WSD, USB). From the port monitor's registry key, readable without admin rights."""
    import re
    import winreg
    h = _open(printer)
    try:
        need = wintypes.DWORD()
        winspool.GetPrinterW(h, 5, None, 0, ctypes.byref(need))               # PRINTER_INFO_5: name, port, …

        class PRINTER_INFO_5(ctypes.Structure):
            _fields_ = [("pPrinterName", wintypes.LPWSTR), ("pPortName", wintypes.LPWSTR), ("Attributes", wintypes.DWORD),
                        ("DeviceNotSelectedTimeout", wintypes.DWORD), ("TransmissionRetryTimeout", wintypes.DWORD)]

        buf = ctypes.create_string_buffer(max(need.value, ctypes.sizeof(PRINTER_INFO_5)))
        _check(winspool.GetPrinterW(h, 5, buf, need, ctypes.byref(need)), "GetPrinter")
        port = (ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_5)).contents.pPortName or "").split(",")[0].strip()
    finally:
        winspool.ClosePrinter(h)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SYSTEM\\CurrentControlSet\\Control\\Print\\Monitors\\"
                            "Standard TCP/IP Port\\Ports\\" + port) as k:
            vals = {}
            for name in ("HostName", "IPAddress", "PortNumber", "Protocol"):
                try:
                    vals[name] = winreg.QueryValueEx(k, name)[0]
                except OSError:
                    pass
    except OSError:
        m = re.fullmatch(r"(?:IP_)?(\d+\.\d+\.\d+\.\d+)(?:_\d+)?", port)        # "IP_192.168.1.50" without a key
        return (m.group(1), 9100) if m else (None, None)
    if vals.get("Protocol", 1) != 1:                                    # 2 = LPR: not the raw 9100 socket
        return None, None
    host = (vals.get("HostName") or vals.get("IPAddress") or "").strip()
    return (host, int(vals.get("PortNumber") or 9100)) if host else (None, None)


def _open(printer):
    h = wintypes.HANDLE()
    _check(winspool.OpenPrinterW(printer, ctypes.byref(h), None), f"opening printer {printer!r}")
    return h


def job(printer, job_id):
    """→ {state: waiting|done|failed, message}. Windows drops a finished job from the queue: gone without an error
    we saw = printed (the driver reports paper out / offline / errors on the job while it's still there)."""
    h = _open(printer)
    try:
        need = wintypes.DWORD()
        winspool.GetJobW(h, int(job_id), 1, None, 0, ctypes.byref(need))
        if not need.value:
            return {"state": "done", "message": ""}                          # no longer in the queue

        class JOB_INFO_1(ctypes.Structure):
            _fields_ = [("JobId", wintypes.DWORD), ("pPrinterName", wintypes.LPWSTR), ("pMachineName", wintypes.LPWSTR),
                        ("pUserName", wintypes.LPWSTR), ("pDocument", wintypes.LPWSTR), ("pDatatype", wintypes.LPWSTR),
                        ("pStatus", wintypes.LPWSTR), ("Status", wintypes.DWORD), ("Priority", wintypes.DWORD),
                        ("Position", wintypes.DWORD), ("TotalPages", wintypes.DWORD), ("PagesPrinted", wintypes.DWORD),
                        ("Submitted", ctypes.c_byte * 16)]

        buf = ctypes.create_string_buffer(need.value)
        if not winspool.GetJobW(h, int(job_id), 1, buf, need, ctypes.byref(need)):
            return {"state": "done", "message": ""}
        j = ctypes.cast(buf, ctypes.POINTER(JOB_INFO_1)).contents
        flags = [v for bit, v in JOB_STATUS.items() if j.Status & bit]
        text = (j.pStatus or "").strip()
        if {"error", "offline", "paper out", "blocked", "needs attention"} & set(flags):
            return {"state": "failed" if "error" in flags or "blocked" in flags else "waiting",
                    "message": text or ", ".join(flags), "flags": flags}
        if "printed" in flags or "complete" in flags:
            return {"state": "done", "message": ""}
        return {"state": "waiting", "message": text or ("printing…" if "printing" in flags else "queued…"), "flags": flags}
    finally:
        winspool.ClosePrinter(h)


def cancel(printer, job_id):
    h = _open(printer)
    try:
        # JOB_CONTROL_DELETE (5): a user may delete their own jobs; CANCEL (3) is the older equivalent
        if not winspool.SetJobW(h, int(job_id), 0, None, 5):
            winspool.SetJobW(h, int(job_id), 0, None, 3)
    finally:
        winspool.ClosePrinter(h)


def printer(name):
    h = _open(name)
    try:
        need = wintypes.DWORD()
        winspool.GetPrinterW(h, 6, None, 0, ctypes.byref(need))              # PRINTER_INFO_6: just the status word
        buf = ctypes.create_string_buffer(max(need.value, 4))
        _check(winspool.GetPrinterW(h, 6, buf, need, ctypes.byref(need)), "GetPrinter")
        status = int.from_bytes(buf.raw[:4], "little")
    finally:
        winspool.ClosePrinter(h)
    reasons = [v for bit, v in PRINTER_STATUS.items() if status & bit]
    return {"state": "stopped" if "paused" in reasons else "idle", "reasons": reasons, "message": ", ".join(reasons),
            "accepting": True}
