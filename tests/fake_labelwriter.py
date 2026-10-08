#!/usr/bin/env python3
"""A stand-in for a networked LabelWriter 550 Turbo / 5XL on port 9100 that speaks just enough of the status
handshake for DYMO's drivers (Fedora CUPS filter and the Windows language monitor) to send the whole job.

The drivers ask ESC A <n> before each page and wait for a 32-byte status; print engine idle, no job lock,
media present, head OK (see LabelWriterLanguageMonitorV2.cpp in dymosoftware/Drivers). Every connection that carries
more than a status poll is saved as <out>/jobN.prn and decoded to <out>/jobN.pbm — the label exactly as it would print.

  python3 tests/fake_labelwriter.py OUTDIR [--bind 127.0.0.1] [--port 9100]
"""
import argparse
import os
import socket
import threading

STATUS = bytearray(32)
STATUS[10] = 8                                              # main bay: media present, OK (Linux only needs "not 1/2/3/5/9/10")
STATUS = bytes(STATUS)


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
            i = data.find(b"\x1bA", start)
            while i != -1:                                    # answer every status request in this chunk
                conn.sendall(STATUS)
                i = data.find(b"\x1bA", i + 2)
    except (socket.timeout, OSError):
        pass
    finally:
        conn.close()
    if len(data) <= 3:                                        # a bare status poll (the Windows port monitor does these)
        return
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9100)
    a = ap.parse_args()
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
