"""Printers that set themselves up, and the roll in each one (dymo.py does the talking).

At start and every few minutes LabelDesk looks for DYMO printers on the network (Bonjour) and keeps its two queues
pointing at them — without anyone running tools/add-printers.sh:
  · a queue's printer moved to a new IP (DHCP)        → the queue is re-pointed (if exactly one such model is around)
  · no queue yet for tags (550 Turbo/550) or shipping (5XL) and exactly one such printer is found → it's added
  · anything else (a second 5XL, a printer of the other kind, two candidates) → offered in Settings, never added silently
Fedora/Mac change CUPS queues with lpadmin (an admin user needs no password); Windows needs an admin prompt, so there
it's always an offer with an Add button. Each change is reported once as an event (the page shows it as a message).

Rolls: the 550 series reports the loaded roll (NFC) — read with the same status request DYMO's driver uses between
jobs, never while that printer is busy, at most every ROLL_EVERY seconds per printer.
Turn it all off with "auto_printers": false in config.json.
"""
import re
import threading
import time
import urllib.parse

import dymo

ROLE_MODELS = {"tag": ("550T", "550"), "ship": ("5XL",)}
MODEL_NAME = {"550T": "LabelWriter 550 Turbo", "550": "LabelWriter 550", "5XL": "LabelWriter 5XL"}
ROLL_EVERY = 30


def socket_host(uri):
    """'socket://192.0.2.5:9100' → ('192.0.2.5', 9100); anything else → (None, None)."""
    m = re.fullmatch(r"socket://([^/:]+)(?::(\d+))?/?", uri or "")
    return (m.group(1), int(m.group(2) or dymo.PORT)) if m else (None, None)


class Auto:
    def __init__(self, ops, browse=dymo.browse, status=dymo.status, sku_info=dymo.sku_info, can_manage=True):
        """ops: queue(kind) → queue name · uri(queue) → device URI or None (no such queue) · add(kind, queue, ip, port,
        model) · repoint(queue, ip, port) · answers(ip, port) → bool · busy(kind) → bool (a job is going to it).
        can_manage False (Windows) = never change anything, only offer."""
        self.ops, self.browse, self.status, self.sku_info, self.can_manage = ops, browse, status, sku_info, can_manage
        self.found, self.offers, self.events, self.at, self.scanning = [], [], [], 0.0, False
        self.lock, self.next_id = threading.Lock(), 1
        self._rolls, self._skus = {}, {}

    # ---- events: shown once by the page
    def event(self, text, level="info"):
        with self.lock:
            self.events.append({"id": self.next_id, "at": time.time(), "text": text, "level": level})
            self.next_id += 1
            self.events = self.events[-30:]

    def since(self, after):
        with self.lock:
            return [e for e in self.events if e["id"] > after]

    # ---- the scan
    def scan(self):
        if self.scanning:
            return
        self.scanning = True
        try:
            found = self.browse()
            self.found, self.at = found, time.time()
            self.offers = self._decide(found)
        finally:
            self.scanning = False

    def _used(self):
        out = {}
        for kind in ROLE_MODELS:
            q = self.ops.queue(kind)
            uri = self.ops.uri(q) if q else None
            out[kind] = (q, uri, socket_host(uri)[0])
        return out

    def _decide(self, found):
        used = self._used()
        in_use = {ip for _q, _u, ip in used.values() if ip}
        for _q, uri, _ip in used.values():                        # dnssd://<Bonjour name>._pdl-datastream…: by name
            if (uri or "").startswith("dnssd://"):
                name = urllib.parse.unquote(uri[8:].split("._", 1)[0])
                in_use |= {p["ip"] for p in found if p["name"] == name}
        offers = []
        for kind, models in ROLE_MODELS.items():
            q, uri, ip = used[kind]
            cands = [p for p in found if p["model"] in models]
            fresh = [p for p in cands if p["ip"] not in in_use]
            what = "tags" if kind == "tag" else "shipping labels"
            if not q or uri is None:                             # no queue for this kind on this PC yet
                if len(fresh) == 1 and self.can_manage:
                    p = fresh[0]
                    try:
                        self.ops.add(kind, q, p["ip"], p["port"], p["model"])
                        in_use.add(p["ip"])
                        self.event(f"Found the DYMO {MODEL_NAME[p['model']]} at {p['ip']} and set it up for {what}.")
                    except Exception as e:                       # noqa: BLE001 — say why, offer it instead
                        self.event(f"Found the DYMO {MODEL_NAME[p['model']]} at {p['ip']} but couldn't add it: {e}", "bad")
                        offers.append(dict(p, kind=kind, why="add"))
                    continue
                offers += [dict(p, kind=kind, why="add") for p in fresh]
                continue
            if ip is None:                                        # dnssd:// or USB: CUPS follows the printer itself
                continue
            if ip in {p["ip"] for p in cands}:                    # its printer is where the queue says
                continue
            if self.ops.answers(ip, socket_host(uri)[1]):         # something answers there and it's not announced:
                continue                                          # leave it alone (Bonjour may just be off)
            if len(fresh) == 1 and self.can_manage:               # gone from its address; exactly one replacement
                p = fresh[0]
                try:
                    self.ops.repoint(q, p["ip"], p["port"])
                    in_use.add(p["ip"])
                    self.event(f"The {MODEL_NAME[p['model']]} moved to {p['ip']} (was {ip}) — LabelDesk follows it now.")
                except Exception as e:                           # noqa: BLE001
                    self.event(f"The {MODEL_NAME[p['model']]} is now at {p['ip']} but LabelDesk couldn't switch to it: {e}", "bad")
                    offers.append(dict(p, kind=kind, why="moved"))
                continue
            offers += [dict(p, kind=kind, why="moved") for p in fresh]
        known = {o["ip"] for o in offers}
        for p in found:                                           # anything else DYMO: list it, don't touch it
            if p["ip"] not in in_use and p["ip"] not in known:
                offers.append(dict(p, kind="tag" if p["model"] in ROLE_MODELS["tag"] else "ship", why="extra"))
        return offers

    # ---- the roll in each printer
    def host_for(self, kind):
        q = self.ops.queue(kind)
        uri = self.ops.uri(q) if q else None
        ip, port = socket_host(uri)
        if ip:
            return ip, port
        if (uri or "").startswith("dnssd://"):
            name = urllib.parse.unquote(uri[8:].split("._", 1)[0])
            named = [p for p in self.found if p["name"] == name]
            if named:
                return named[0]["ip"], named[0]["port"]
        cands = [p for p in self.found if p["model"] in ROLE_MODELS[kind]]
        return (cands[0]["ip"], cands[0]["port"]) if len(cands) == 1 else (None, None)

    def roll(self, kind, now=None):
        """→ {stock, sku, remaining, low, media, canPrint, widthMm, lengthMm} or None (unknown). Cached."""
        now = time.time() if now is None else now
        hit = self._rolls.get(kind)
        if hit and now - hit[0] < ROLL_EVERY:
            return hit[1]
        ip, port = self.host_for(kind)
        if not ip or self.ops.busy(kind):
            return hit[1] if hit else None
        try:
            st = self.status(ip, port)
        except (OSError, ValueError):
            self._rolls[kind] = (now, None)
            return None
        if st["engine"] not in ("idle",):                         # someone is printing: ask again later
            return hit[1] if hit else None
        info = self._skus.get(st["sku"]) if st["sku"] else None
        if st["sku"] and st["sku"] not in self._skus:
            try:
                info = self._skus[st["sku"]] = self.sku_info(ip, port) or {}
            except (OSError, ValueError):
                info = {}
        info = info or {}
        stock = dymo.stock_for(st["sku"] or info.get("sku", ""), info.get("widthMm", 0), info.get("lengthMm", 0))
        r = {"stock": stock, "name": dymo.describe_roll(stock) or st["sku"], "sku": st["sku"],
             "remaining": st["remaining"], "low": st["low"], "media": st["media"], "canPrint": st["canPrint"],
             "widthMm": info.get("widthMm"), "lengthMm": info.get("lengthMm")}
        self._rolls[kind] = (now, r)
        return r

    def forget_roll(self, kind):
        self._rolls.pop(kind, None)

    # ---- background
    def run(self, every=300, first_delay=2):
        time.sleep(first_delay)
        while True:
            try:
                self.scan()
            except Exception as e:                               # noqa: BLE001 — never let the watcher die
                print("printers:", repr(e), flush=True)
            time.sleep(every)
