#!/usr/bin/env python3
"""End-to-end check of "printers set themselves up" against a RUNNING LabelDesk whose queues don't exist yet and two
fake LabelWriters that announce themselves on Bonjour:

    python3 tests/fake_labelwriter.py /tmp/ldjobs --bind 127.0.0.1 --mdns "DYMO LabelWriter 550 Turbo" --roll 30252 &
    python3 tests/fake_labelwriter.py /tmp/ldjobs --bind 127.0.0.2 --mdns "DYMO LabelWriter 5XL" --roll 1744907 &
    python3 tests/auto_check.py [--url http://127.0.0.1:8792]      # then tests/print_check.py prints through them

Passes when LabelDesk found both, added both queues by itself (events say so), and reads each roll + labels left.
"""
import argparse
import json
import sys
import time
import urllib.request


def call(url, path, body=None):
    req = urllib.request.Request(f"{url}/api/{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8792")
    ap.add_argument("--wait", type=int, default=60)
    ap.add_argument("--queues-by-hand", action="store_true",
                    help="the queues were added with tools/add-printers.sh (macOS: Local Network privacy blocks the scan)")
    a = ap.parse_args()
    deadline, p = time.time() + a.wait, {}
    while time.time() < deadline:
        p = call(a.url, "printers")
        rolls = [p[k].get("roll") or {} for k in ("tag", "ship")]
        if all(p[k]["ok"] for k in ("tag", "ship")) and all(r.get("stock") for r in rolls):
            break
        if time.time() > deadline - a.wait + 15 and not p["network"]["found"]:
            call(a.url, "printers/scan", {})                       # nudge: scan now instead of waiting 5 minutes
        time.sleep(2)
    events = [e["text"] for e in call(a.url, "printers/events?after=0")["events"]]
    print("found:", [(f["model"], f["ip"]) for f in p.get("network", {}).get("found", [])], "· scan error:", p.get("network", {}).get("error"))
    print("events:", *events, sep="\n  ")
    problems = []
    for kind, stock in (("tag", "30252"), ("ship", "1744907")):
        r = p.get(kind, {}).get("roll") or {}
        print(f"{kind}: {p.get(kind, {}).get('status')} · roll {r.get('stock')} · {r.get('remaining')} left")
        if not p.get(kind, {}).get("ok"):
            problems.append(f"{kind} queue not working: {p.get(kind, {}).get('status')}")
        if r.get("stock") != stock or not r.get("remaining"):
            problems.append(f"{kind}: expected roll {stock} with a count, got {r}")
    if not a.queues_by_hand and sum("set it up" in e for e in events) != 2:
        problems.append("expected two 'set it up' events")
    for x in problems:
        print("✗", x)
    print("✓ printers set themselves up and report their rolls" if not problems else "")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
