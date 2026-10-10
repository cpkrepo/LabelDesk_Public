#!/usr/bin/env python3
"""A stand-in for a networked LabelWriter 550 Turbo / 5XL on port 9100 that speaks just enough of the status
handshake for DYMO's drivers (Fedora CUPS filter and the Windows language monitor) to send the whole job.

The drivers ask ESC A <n> before each page and wait for a 32-byte status; print engine idle, no job lock,
media present, head OK (see LabelWriterLanguageMonitorV2.cpp in dymosoftware/Drivers). Every connection that carries
more than a status poll is saved as <out>/jobN.prn and decoded to <out>/jobN.pbm — the label exactly as it would print.

  python3 tests/fake_labelwriter.py OUTDIR [--bind 127.0.0.1] [--port 9100] [--roll 30252] [--left 500]
                                    [--mdns "DYMO LabelWriter 5XL"]

Like a real 550 it reports the loaded roll (SKU, labels left — one fewer per label printed) in its status and answers
ESC U with the roll's NFC data (sizes in mm), per DYMO's Technical Reference. --roll none = no roll loaded.
--mdns announces it on Bonjour (_pdl-datastream._tcp) under that name, for LabelDesk's automatic printer setup.
"""
import argparse
import os
import socket
import struct
import threading

ROLL = {"sku": "30252", "left": 500}
SIZES = {"30252": (28, 89, 350), "30321": (36, 89, 260), "1744907": (102, 152, 220)}   # width, length mm; labels per roll


def status():
    st = bytearray(32)
    st[8] = 0                                               # head OK
    st[10] = 8 if ROLL["sku"] else 2                        # main bay: media present, OK / no media
    st[11:23] = ROLL["sku"].encode().ljust(12, b"\0")[:12]
    struct.pack_into("<H", st, 27, ROLL["left"] if ROLL["sku"] else 0)
    return bytes(st)


def sku_reply():
    b = bytearray(63)
    if ROLL["sku"]:
        w, l, total = SIZES.get(ROLL["sku"], (0, 0, 0))
        b[0:2], b[3] = b"\xb6\xca", 63
        b[8:20] = ROLL["sku"].encode().ljust(12, b"\0")[:12]
        b[21], b[22], b[23], b[24] = 0xFF, 3, 1, 1           # global, paper, die-cut, white
        struct.pack_into("<HHH", b, 40, l, w, 0)
        struct.pack_into("<H", b, 50, total)
    return bytes(b)


def decode(data):
    """The label as the printer would print it → (cols, rows, PBM bytes) or None. The 550 driver sends one or more bands
    (a 4×6 comes in two): ESC D 01 02 <lines, LE32> <dots per line, LE32> then lines × ceil(dots/8) bytes, 1 = black."""
    rows, cols, body, i = 0, 0, bytearray(), data.find(b"\x1bD\x01\x02")
    while i >= 0:
        n, c = int.from_bytes(data[i + 4:i + 8], "little"), int.from_bytes(data[i + 8:i + 12], "little")
        stride = (c + 7) // 8
        band = data[i + 12:i + 12 + n * stride]
        if not n or (cols and c != cols) or len(band) < n * stride:
            break
        rows, cols = rows + n, c
        body += band
        i = data.find(b"\x1bD\x01\x02", i + 12 + n * stride)
    return (cols, rows, b"P4\n%d %d\n" % (cols, rows) + bytes(body)) if rows else None


def serve(conn, out, counter, lock):
    conn.settimeout(6)
    data = bytearray()
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            start = max(0, len(data) - 2)
            data += chunk
            if data[:2] == b"\x1bU" and start == 0:          # roll info (a separate, read-only request)
                conn.sendall(sku_reply())
            i = data.find(b"\x1bA", start)
            while i != -1:                                    # answer every status request in this chunk
                conn.sendall(status())
                i = data.find(b"\x1bA", i + 2)
    except (socket.timeout, OSError):
        pass
    finally:
        conn.close()
    if len(data) <= 3:                                        # a bare status / roll poll (the Windows port monitor does these)
        return
    ROLL["left"] = max(0, ROLL["left"] - max(1, data.count(b"\x1bE") + data.count(b"\x1bG")))
    with lock:
        counter[0] += 1
        n = counter[0]
    path = os.path.join(out, f"job{n}.prn")
    with open(path, "wb") as f:
        f.write(data)
    img = decode(data)
    if img:
        with open(path[:-4] + ".pbm", "wb") as f:
            f.write(img[2])
    print(f"job{n}: {len(data)} bytes" + (f", label {img[0]}×{img[1]} dots → {path[:-4]}.pbm" if img else " (no raster)")
          + f"  [{path}]", flush=True)


def announce(name, ip, port):
    """A tiny mDNS responder: answers PTR queries for _pdl-datastream._tcp with this printer (unicast to the asker)."""
    def qname(n):
        return b"".join(bytes([len(p)]) + p for p in (x.encode() for x in n.split(".") if x)) + b"\0"
    svc, host = "_pdl-datastream._tcp.local", "fake-" + "".join(c for c in name if c.isalnum()).lower() + ".local"
    inst = f"{name}.{svc}"
    def rr(n, rtype, data, cls=1):
        return qname(n) + struct.pack(">HHIH", rtype, cls, 120, len(data)) + data
    txt = b"".join(bytes([len(t)]) + t for t in (f"ty={name}".encode(), b"product=(" + name.encode() + b")"))
    answer = struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 3) + rr(svc, 12, qname(inst)) + \
        rr(inst, 33, struct.pack(">HHH", 0, 0, port) + qname(host)) + rr(inst, 16, txt) + rr(host, 1, socket.inet_aton(ip))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    s.bind(("", 5353))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton("224.0.0.251") + socket.inet_aton("0.0.0.0"))
    print(f"announcing {inst} → {ip}:{port}", flush=True)
    while True:
        q, sender = s.recvfrom(9000)
        if len(q) > 12 and not q[2] & 0x80 and b"_pdl-datastream" in q:
            s.sendto(q[:2] + answer[2:], sender)              # same query id, straight back to the asker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9100)
    ap.add_argument("--roll", default="30252", help="SKU of the loaded roll (30252, 30321, 1744907) or none")
    ap.add_argument("--left", type=int, default=500)
    ap.add_argument("--mdns", metavar="NAME", help='announce on Bonjour, e.g. "DYMO LabelWriter 5XL"')
    a = ap.parse_args()
    ROLL.update(sku="" if a.roll == "none" else a.roll, left=a.left)
    if a.mdns:
        threading.Thread(target=announce, args=(a.mdns, "127.0.0.1" if a.bind in ("0.0.0.0", "") else a.bind, a.port),
                         daemon=True).start()
    os.makedirs(a.out, exist_ok=True)
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((a.bind, a.port))
    s.listen(8)
    print(f"fake LabelWriter on {a.bind}:{a.port} → {a.out}", flush=True)
    counter, lock = [0], threading.Lock()
    while True:
        c, _ = s.accept()
        threading.Thread(target=serve, args=(c, a.out, counter, lock), daemon=True).start()


if __name__ == "__main__":
    main()
