"""Where this PC keeps the ConnectWise API keys — never in the repo, never in config.json.

  Fedora/Linux: the login keyring (libsecret `secret-tool`, unlocked when the user logs in)
  macOS:        the login Keychain (`security`, generic password "LabelDesk ConnectWise"; the secret goes in on stdin)
  Windows:      DPAPI (CryptProtectData, per Windows user) → %APPDATA%\\LabelDesk\\connectwise.bin
  Fallback:     ~/.config/labeldesk/connectwise.json (Mac: ~/Library/Application Support/LabelDesk/), mode 0600
                (headless / no keyring) — reported as such in Settings
Set LABELDESK_KEYS=file to force the file (tests).
"""
import base64
import json
import os
import subprocess
import sys

ATTRS = ["application", "labeldesk", "secret", "connectwise"]
FILE = os.path.expanduser("~/Library/Application Support/LabelDesk/connectwise.json" if sys.platform == "darwin"
                          else "~/.config/labeldesk/connectwise.json")
KEYCHAIN = ["-s", "LabelDesk ConnectWise", "-a", "connectwise"]


_detected = []


def _backend():
    forced = os.environ.get("LABELDESK_KEYS")
    if forced:
        return forced
    if not _detected:                                            # once per process
        b = "dpapi" if sys.platform == "win32" else "keychain" if sys.platform == "darwin" else "file"
        if b == "file":
            try:
                if subprocess.run(["secret-tool", "--version"], capture_output=True, timeout=5).returncode in (0, 1):
                    b = "keyring"
            except (OSError, subprocess.SubprocessError):
                pass
        _detected.append(b)
    return _detected[0]


# ---- Windows DPAPI (ctypes, no pywin32)
def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src, out = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None if not protect else "LabelDesk", None, None, None, 0x1, ctypes.byref(out)):
        raise OSError("Windows couldn't " + ("encrypt" if protect else "decrypt") + " the ConnectWise keys")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _win_file():
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LabelDesk", "connectwise.bin")


def load():
    """→ dict (company, public, private, client_id) or {}."""
    b = _backend()
    try:
        if b == "keyring":
            r = subprocess.run(["secret-tool", "lookup", *ATTRS], capture_output=True, text=True, timeout=10)
            return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
        if b == "keychain":
            r = subprocess.run(["security", "find-generic-password", *KEYCHAIN, "-w"], capture_output=True, text=True, timeout=10)
            return json.loads(base64.b64decode(r.stdout.strip())) if r.returncode == 0 and r.stdout.strip() else {}
        if b == "dpapi":
            with open(_win_file(), "rb") as f:
                return json.loads(_dpapi(f.read(), protect=False))
        with open(FILE) as f:
            return json.load(f)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def save(creds):
    b, data = _backend(), json.dumps(creds)
    if b == "keyring":
        r = subprocess.run(["secret-tool", "store", "--label=LabelDesk ConnectWise API keys", *ATTRS],
                           input=data, capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return "login keyring"
        b = "file"                                            # no keyring daemon (headless) → fall back, and say so
    if b == "keychain":
        # `security -i` reads the command from stdin, so the keys never appear in a process list; base64 = no quoting
        cmd = ('add-generic-password -U -s "LabelDesk ConnectWise" -a connectwise -l "LabelDesk ConnectWise API keys" '
               f'-w {base64.b64encode(data.encode()).decode()}\n')
        r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and load():
            return "Mac Keychain"
        b = "file"
    if b == "dpapi":
        os.makedirs(os.path.dirname(_win_file()), exist_ok=True)
        with open(_win_file(), "wb") as f:
            f.write(_dpapi(data.encode(), protect=True))
        return "Windows (encrypted for this user)"
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    fd = os.open(FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)
    os.chmod(FILE, 0o600)
    return "private file (no keyring available)"


def clear():
    b = _backend()
    if b == "keyring":
        subprocess.run(["secret-tool", "clear", *ATTRS], capture_output=True, timeout=10)
    if b == "keychain":
        subprocess.run(["security", "delete-generic-password", *KEYCHAIN], capture_output=True, timeout=10)
    for p in (FILE, _win_file()):
        try:
            os.unlink(p)
        except OSError:
            pass
