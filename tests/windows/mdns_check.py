"""Run ON WINDOWS (the test VM): announce two fake DYMO printers through Windows' DNS-SD and find them with
server/winmdns.browse() — proves the ctypes structures, callbacks and resolve on a real Windows.
    python tests/windows/mdns_check.py     (LabelDesk's embedded python works: python\\python.exe)"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "server"))
import winmdns  # noqa: E402

keep = [winmdns.register("DYMO LabelWriter 5XL (VM test)", 9101, "127.0.0.1", {"ty": "DYMO LabelWriter 5XL"}),
        winmdns.register("DYMOLW550T0A1B2C", 9100, "127.0.0.1", {"ty": "DYMO LabelWriter 550 Turbo"}),
        winmdns.register("Brother HL-2350 (VM test)", 9102, "127.0.0.1")]
time.sleep(1)
found = winmdns.browse(4)
print("found:", found)
models = sorted(p["model"] for p in found)
ok = models == ["550T", "5XL"] and all(p["ip"] and p["port"] in (9100, 9101) for p in found)   # Windows gives the host's own address
print("OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
