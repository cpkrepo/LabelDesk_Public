#!/usr/bin/env python3
"""Ask a networked LabelWriter 550 / 550 Turbo / 5XL for its 32-byte status and show it. READ-ONLY: it sends the same
status request DYMO's own driver sends between jobs (ESC A 0 = "status, no lock"; see LabelWriterLanguageMonitorV2.cpp
in github.com/dymosoftware/Drivers) and nothing else, so it can't start, hold or cancel a print.

Purpose: find out whether the status reply carries a labels-remaining count (the 550 series reads the roll's NFC chip)
before LabelDesk shows one. DYMO's driver only reads bytes 0-4, 8, 10 and 21; the meaning of the others is unknown.
    tools/dymo-status.py 192.0.2.10                 # one reading
    tools/dymo-status.py 192.0.2.10 --save a.json   # save it; print a few labels; then:
    tools/dymo-status.py 192.0.2.10 --compare a.json   # which bytes changed, and by how much
A byte (or byte pair) that drops by exactly the number of labels printed is the candidate counter.
"""
import argparse
import json
import socket
import sys

ENGINE = {0: "idle", 3: "cancelling"}                                            # status[0] & 7: only these two are named in DYMO's source
BAY = {1: "bay open", 2: "no media", 3: "media not inserted properly", 5: "media empty", 9: "media jammed / slot error",
       10: "counterfeit (non-DYMO) media"}                                              # status[10] & 0xF; anything else = OK
HEAD = {0: "OK", 1: "overheated"}                                                         # status[8] & 3
VOLTAGE = {4: "too low"}                                                                  # status[21] & 0xF


def read_status(host, port=9100, timeout=5.0):
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(b"\x1bA\x00")
        data = b""
        while len(data) < 32:
            chunk = s.recv(32 - len(data))
            if not chunk:
                break
            data += chunk
    if len(data) != 32:
        raise RuntimeError(f"expected 32 status bytes, got {len(data)} ({data.hex(' ')})")
    return data


def describe(st):
    job = int.from_bytes(st[1:5], "little")
    lines = [f"engine:  {ENGINE.get(st[0] & 7, f"other ({st[0] & 7})")}   job id: {job}",
             f"media:   {BAY.get(st[10] & 0xF, f'OK ({st[10] & 0xF})')}",
             f"head:    {HEAD.get(st[8] & 3, f'unknown ({st[8] & 3})')}   voltage: {VOLTAGE.get(st[21] & 0xF, 'OK')}",
             "bytes:   " + " ".join(f"{i:02d}:{b:02x}" for i, b in enumerate(st[:16])),
             "         " + " ".join(f"{i:02d}:{b:02x}" for i, b in enumerate(st[16:], 16))]
    return "\n".join(lines)


def compare(old, new):
    out = []
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b:
            out.append(f"byte {i:02d}: {a} → {b} ({b - a:+d})")
    for i in range(31):                                             # 16-bit little-endian pairs, in case it's a counter > 255
        a, b = old[i] | old[i + 1] << 8, new[i] | new[i + 1] << 8
        if a != b and (old[i + 1] != new[i + 1]):
            out.append(f"bytes {i:02d}-{i + 1:02d} (LE16): {a} → {b} ({b - a:+d})")
    return "\n".join(out) or "no byte changed"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=9100)
    ap.add_argument("--save", metavar="FILE")
    ap.add_argument("--compare", metavar="FILE")
    a = ap.parse_args(argv)
    try:
        st = read_status(a.host, a.port)
    except (OSError, RuntimeError) as e:
        print(f"✗ {a.host}:{a.port}: {e}", file=sys.stderr)
        return 1
    print(describe(st))
    if a.save:
        with open(a.save, "w") as f:
            json.dump(list(st), f)
        print(f"saved to {a.save}")
    if a.compare:
        with open(a.compare) as f:
            print("changed since " + a.compare + ":\n" + compare(bytes(json.load(f)), st))
    return 0


if __name__ == "__main__":
    sys.exit(main())
