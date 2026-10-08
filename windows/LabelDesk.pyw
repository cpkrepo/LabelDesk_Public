"""LabelDesk for Windows — the Start-menu entry. Starts the background server if it isn't running, then opens LabelDesk
in its own Microsoft Edge window (no tabs / address bar). Runs under pythonw.exe (no console window)."""
import os
import socket
import subprocess
import sys
import time
import webbrowser

URL = "http://127.0.0.1:8792"
HERE = os.path.dirname(os.path.abspath(__file__))
NO_WINDOW, DETACHED = 0x08000000, 0x00000008


def up():
    try:
        with socket.create_connection(("127.0.0.1", 8792), timeout=0.5):
            return True
    except OSError:
        return False


def edge():
    """msedge.exe from App Paths (per machine or per user), else the usual install folders."""
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
                path = winreg.QueryValue(k, None)
                if os.path.isfile(path):
                    return path
        except OSError:
            pass
    for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "")):
        p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
        if base and os.path.isfile(p):
            return p
    return None


def window_args():
    """Fit the window inside the work area (above the taskbar) — the job bar lives at the bottom of the window."""
    try:
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):     # SPI_GETWORKAREA
            w, h = min(1280, r.right - r.left), min(860, r.bottom - r.top)
            return [f"--window-size={w},{h}", f"--window-position={r.left + (r.right - r.left - w) // 2},{r.top}"]
    except (OSError, AttributeError):
        pass
    return ["--window-size=1200,720"]


if not up():
    subprocess.Popen([sys.executable, os.path.join(HERE, "labeldesk-server.pyw")], cwd=HERE,
                     creationflags=NO_WINDOW | DETACHED, close_fds=True)
    for _ in range(40):
        if up():
            break
        time.sleep(0.25)
browser = edge()
if browser:
    subprocess.Popen([browser, f"--app={URL}", *window_args()], close_fds=True)
else:
    webbrowser.open(URL)
