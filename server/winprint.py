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


def _check(ok, what):
    if not ok:
        raise RuntimeError(f"{what} failed (Windows error {ctypes.get_last_error()})")


class DOCINFOW(ctypes.Structure if sys.platform == "win32" else object):
    if sys.platform == "win32":
        _fields_ = [("cbSize", ctypes.c_int), ("lpszDocName", wintypes.LPCWSTR), ("lpszOutput", wintypes.LPCWSTR),
                    ("lpszDatatype", wintypes.LPCWSTR), ("fwType", wintypes.DWORD)]


def find():
    """Installed DYMO 550 Turbo / 5XL printers (EnumPrinters: local + network connections), by printer name, else by
    driver name — users rename them ("Asset Tags", "Shipping Labels"); the driver keeps saying "LabelWriter 5XL"."""
    PRINTER_ENUM_LOCAL, PRINTER_ENUM_CONNECTIONS = 0x2, 0x4
    need, got = wintypes.DWORD(), wintypes.DWORD()
    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    winspool.EnumPrintersW(flags, None, 2, None, 0, ctypes.byref(need), ctypes.byref(got))
    buf = ctypes.create_string_buffer(need.value)
    _check(winspool.EnumPrintersW(flags, None, 2, buf, need, ctypes.byref(need), ctypes.byref(got)), "EnumPrinters")

    class PRINTER_INFO_2(ctypes.Structure):
        _fields_ = [(f, wintypes.LPWSTR) for f in ("pServerName", "pPrinterName", "pShareName", "pPortName",
                                                    "pDriverName", "pComment", "pLocation")] + \
                   [("pDevMode", ctypes.c_void_p)] + \
                   [(f, wintypes.LPWSTR) for f in ("pSepFile", "pPrintProcessor", "pDatatype", "pParameters")] + \
                   [("pSecurityDescriptor", ctypes.c_void_p)] + \
                   [(f, wintypes.DWORD) for f in ("Attributes", "Priority", "DefaultPriority", "StartTime",
                                                   "UntilTime", "Status", "cJobs", "AveragePPM")]

    printers = [(p.pPrinterName, (p.pDriverName or "").lower())
                for p in ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_2 * got.value)).contents]
    names = [n for n, _ in printers]

    def pick(*words):
        return (next((n for n, _ in printers if all(w in n.lower() for w in words)), None)
                or next((n for n, d in printers if "dymo" in d and all(w in d for w in words)), None))

    return {"tag": pick("550", "turbo") or pick("550"), "ship": pick("5xl"), "all": names}


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
    """Print one label. gray = (width, height, bytes: one 0-255 value per pixel, rows top-down) at 300 dpi."""
    w, h, pixels = gray
    dm, paper = _devmode(printer, kind, copies, paper)
    hdc = gdi32.CreateDCW("WINSPOOL", printer, None, dm)
    _check(hdc, f"opening {printer}")
    try:
        di = DOCINFOW(ctypes.sizeof(DOCINFOW), title, None, None, 0)
        job = gdi32.StartDocW(hdc, ctypes.byref(di))
        _check(job > 0, "StartDoc")
        _check(gdi32.StartPage(hdc) > 0, "StartPage")
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
        gdi32.SetStretchBltMode(hdc, 4)                                      # HALFTONE
        _check(gdi32.StretchDIBits(hdc, x, y, dw, dh, 0, 0, w, h, bits, ctypes.byref(bmi), 0, 0x00CC0020) != 0,
               "StretchDIBits")                                              # DIB_RGB_COLORS, SRCCOPY
        _check(gdi32.EndPage(hdc) > 0, "EndPage")
        _check(gdi32.EndDoc(hdc) > 0, "EndDoc")
        return str(job), paper
    finally:
        gdi32.DeleteDC(hdc)


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
