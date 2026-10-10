"""Talking to the DYMO LabelWriter 550 series on the network directly (standard library only, every platform):

  browse()       Bonjour/mDNS: which DYMO printers are on this network, their model and IP address
  status()       the 32-byte print engine status (ESC A 0 = "status, no lock": the same request DYMO's driver sends
                 between jobs — it can't start, hold or cancel a print): media state, loaded roll's SKU, labels left
  sku_info()     the loaded roll from its NFC chip (ESC U, 63 bytes): SKU, label width/length in mm, total count
  stock_for()    which of LabelDesk's label stocks that roll is

Byte layouts: DYMO "LabelWriter 550 Series Printers Technical Reference Manual" (2021), Print Status Response and
ESC U. Status: 0 engine (0 idle, 1 printing, 2 error, 3 cancel, 4 busy, 5 unlock) · 1–4 job id · 8 head · 10 main bay
(media state) · 11–22 SKU (text) · 23–26 error id · 27–28 labels remaining (u16) · 30 head voltage. Not yet checked
against the shop's real printers (docs/dev/open-items.md) — every value is used defensively.
"""
import random
import re
import socket
import struct
import time

PORT = 9100
MDNS = ("224.0.0.251", 5353)
SERVICES = ["_pdl-datastream._tcp.local", "_printer._tcp.local", "_ipp._tcp.local"]

ENGINE = {0: "idle", 1: "printing", 2: "error", 3: "cancelling", 4: "busy", 5: "unlocking"}
BAY = {0: "unknown", 1: "the cover is open", 2: "no labels loaded", 3: "the labels aren't loaded properly",
       4: "labels loaded", 5: "the roll is empty", 6: "the roll is almost empty", 7: "the roll is running low",
       8: "ok", 9: "the labels are jammed", 10: "the roll isn't a genuine DYMO roll"}
BAY_OK = {4, 6, 7, 8}                                            # can print (6/7 = low: say so, don't block)


# ------------------------------------------------------------------ status + roll
def _ask(host, cmd, size, port=PORT, timeout=2.0):
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(cmd)
        data = b""
        while len(data) < size:
            chunk = s.recv(size - len(data))
            if not chunk:
                break
            data += chunk
    return data


def _text(b):
    t = b.split(b"\0", 1)[0].decode("ascii", "replace").strip()
    return t if re.fullmatch(r"[0-9A-Za-z_.\- ]{1,12}", t or "") else ""


def parse_status(st):
    if len(st) != 32:
        raise ValueError(f"expected 32 status bytes, got {len(st)}")
    remaining = struct.unpack_from("<H", st, 27)[0]
    bay = st[10] & 0x0F
    return {"engine": ENGINE.get(st[0], f"other ({st[0]})"), "job": struct.unpack_from("<I", st, 1)[0],
            "bay": bay, "media": BAY.get(bay, f"unknown ({bay})"), "canPrint": bay in BAY_OK,
            "low": bay in (6, 7), "sku": _text(st[11:23]), "remaining": remaining if 0 < remaining < 0xFFFF else None,
            "error": struct.unpack_from("<I", st, 23)[0], "headOk": (st[8] & 3) in (0, 2)}


def status(host, port=PORT, timeout=1.5):
    return parse_status(_ask(host, b"\x1bA\x00", 32, port, timeout))


def parse_sku(b):
    """ESC U reply → {sku, widthMm, lengthMm, total} or None (no roll / no NFC data)."""
    if len(b) < 56 or b[0:2] not in (b"\xb6\xca", b"\xca\xb6"):    # magic 0xCAB6 (byte order isn't spelled out)
        return None
    u16 = lambda i: struct.unpack_from("<H", b, i)[0]          # noqa: E731
    return {"sku": _text(b[8:20]), "material": b[22], "lengthMm": u16(40), "widthMm": u16(42), "total": u16(50)}


def sku_info(host, port=PORT, timeout=2.0):
    return parse_sku(_ask(host, b"\x1bU", 63, port, timeout))


# the label stocks LabelDesk prints on, by DYMO SKU and by size (mm, either way round) — the size is the fallback
STOCKS = {"30252": (28, 89), "30321": (36, 89), "1744907": (102, 152)}


def stock_for(sku="", width_mm=0, length_mm=0):
    """→ '30252' / '30321' / '1744907' or '' (some other roll, or nothing known)."""
    for code in STOCKS:
        if code in (sku or ""):
            return code
    if width_mm and length_mm:
        a, b = sorted((width_mm, length_mm))
        for code, (w, l) in STOCKS.items():
            if abs(a - w) <= 2 and abs(b - l) <= 3:
                return code
    return ""


def describe_roll(code):
    return {"30252": "30252 Address (1-1/8\" × 3-1/2\")", "30321": "30321 Large Address (1.4\" × 3.5\")",
            "1744907": "1744907 Shipping (4\" × 6\")"}.get(code, "")


# ------------------------------------------------------------------ Bonjour / mDNS browse
def model_of(text):
    """'DYMO LabelWriter 550 Turbo' / 'DYMOLW550T1A2B3C' / 'LabelWriter 5XL' → '550T' / '5XL' / '550' / ''."""
    t = (text or "").upper().replace(" ", "")
    if "DYMO" not in t and "LABELWRITER" not in t:
        return ""
    if "5XL" in t:
        return "5XL"
    if "550TURBO" in t or "550T" in t:
        return "550T"
    return "550" if "550" in t else ""


def _name(msg, i):
    """DNS name at offset i (with compression) → (name, offset after it)."""
    labels, jumped, end = [], False, None
    for _ in range(64):
        n = msg[i]
        if n == 0:
            i += 1
            break
        if n & 0xC0 == 0xC0:
            if not jumped:
                end = i + 2
            i, jumped = ((n & 0x3F) << 8) | msg[i + 1], True
            continue
        labels.append(msg[i + 1:i + 1 + n].decode("utf-8", "replace"))
        i += 1 + n
    return ".".join(labels), (end if jumped else i)


def _qname(name):
    return b"".join(bytes([len(p)]) + p for p in (x.encode() for x in name.split(".") if x)) + b"\0"


def query(services=SERVICES):
    """One mDNS query packet: PTR for each service type, 'unicast response' bit set."""
    out = struct.pack(">HHHHHH", 0, 0, len(services), 0, 0, 0)
    for s in services:
        out += _qname(s) + struct.pack(">HH", 12, 0x8001)        # PTR, IN + QU
    return out


def parse_answers(msg):
    """All records in an mDNS response → list of (name, type, value)."""
    _id, _flags, qd, an, ns, ar = struct.unpack_from(">HHHHHH", msg, 0)
    i, out = 12, []
    for _ in range(qd):
        _, i = _name(msg, i)
        i += 4
    for _ in range(an + ns + ar):
        name, i = _name(msg, i)
        rtype, _cls, _ttl, rdlen = struct.unpack_from(">HHIH", msg, i)
        i += 10
        rd = msg[i:i + rdlen]
        if rtype == 12:                                          # PTR
            out.append((name, "PTR", _name(msg, i)[0]))
        elif rtype == 33:                                        # SRV
            out.append((name, "SRV", (_name(msg, i + 6)[0], struct.unpack_from(">H", rd, 4)[0])))
        elif rtype == 1 and rdlen == 4:                          # A
            out.append((name, "A", socket.inet_ntoa(rd)))
        elif rtype == 16:                                        # TXT
            txt, j = [], 0
            while j < len(rd):
                txt.append(rd[j + 1:j + 1 + rd[j]].decode("utf-8", "replace"))
                j += 1 + rd[j]
            out.append((name, "TXT", txt))
        i += rdlen
    return out


def collect(records):
    """mDNS records → DYMO printers [{name, model, ip, port, host}] (one per IP)."""
    ptr = [v for _n, t, v in records if t == "PTR"]
    srv = {n: v for n, t, v in records if t == "SRV"}
    txt = {n: v for n, t, v in records if t == "TXT"}
    a = {n.lower(): v for n, t, v in records if t == "A"}
    found = {}
    for inst in ptr + list(srv):
        host, port = srv.get(inst, ("", 0))
        label = inst.split("._", 1)[0]
        extra = " ".join(x for x in txt.get(inst, []) if x.lower().startswith(("ty=", "product=", "usb_mdl=")))
        model = model_of(f"{label} {extra} {host}")
        ip = a.get(host.lower(), "")
        if not model or not ip:
            continue
        raw = inst.startswith(label + "._pdl-datastream.")
        cur = found.get(ip)
        if not cur or raw:                                       # prefer the raw-printing (port 9100) entry
            found[ip] = {"name": label, "model": model, "ip": ip, "port": port if raw else PORT, "host": host}
    return list(found.values())


def browse_cups(seconds=20):
    """Ask CUPS which DYMO printers it sees on Bonjour (`lpinfo --include-schemes dnssd -v`). For the Mac: cupsd is a
    system daemon, so macOS's Local Network privacy (which stops LabelDesk's own scan from its LaunchAgent) doesn't apply.
    → [{name, model, uri, port}] (no IP: queues use the dnssd:// URI and CUPS finds the printer each time)."""
    import subprocess
    import urllib.parse
    try:
        out = subprocess.run(["lpinfo", "--include-schemes", "dnssd", "-v"], capture_output=True, text=True, timeout=seconds).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_lpinfo(out)


def parse_lpinfo(out):
    import urllib.parse
    found = {}
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[1].startswith("dnssd://"):
            continue
        uri = parts[1].strip()
        name = urllib.parse.unquote(uri[8:].split("._", 1)[0])
        model = model_of(name)
        if model and ("._pdl-datastream." in uri or name not in found):   # prefer raw printing (port 9100) like the scan
            found[name] = {"name": name, "model": model, "uri": uri.split("?", 1)[0] if "._pdl-datastream." in uri else uri,
                           "port": PORT}
    return list(found.values())


LAST = {"error": None}                                           # why the last browse found nothing (shown in Settings)


def browse(seconds=3.0):
    """Ask the network which DYMO printers are there. → [{name, model, ip, port, host}]. Never raises."""
    records, LAST["error"] = [], None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s.bind(("", 0))                                          # legacy unicast query: answers come back to us
        s.settimeout(0.3)
        q = bytearray(query())
        q[0:2] = struct.pack(">H", random.randint(1, 0xFFFF))
        end, sent = time.time() + seconds, 0
        while time.time() < end:
            if sent < 3 and time.time() > end - seconds + sent * 0.8:
                s.sendto(bytes(q), MDNS)
                sent += 1
            try:
                msg, _ = s.recvfrom(9000)
                records += parse_answers(msg)
            except socket.timeout:
                continue
            except (ValueError, IndexError, struct.error):
                continue
        s.close()
    except OSError as e:                                         # e.g. macOS Local Network privacy: "No route to host"
        LAST["error"] = f"{e.strerror or e}"
    return collect(records)
