"""dymo.py (status/roll bytes, Bonjour answers) and autoprint.py (what LabelDesk changes by itself) — no network, no CUPS.
The real thing — Bonjour, lpadmin, a print — runs in CI on a Mac against tests/fake_labelwriter.py --mdns."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
import autoprint  # noqa: E402
import dymo  # noqa: E402


def status_bytes(bay=8, sku="30252", left=312, engine=0):
    st = bytearray(32)
    st[0], st[10] = engine, bay
    st[11:23] = sku.encode().ljust(12, b"\0")
    struct.pack_into("<H", st, 27, left)
    return bytes(st)


def qname(n):
    return b"".join(bytes([len(p)]) + p.encode() for p in n.split(".") if p) + b"\0"


def rr(n, rtype, data):
    return qname(n) + struct.pack(">HHIH", rtype, 1, 120, len(data)) + data


def announcement(name, ip, port=9100, svc="_pdl-datastream._tcp.local", txt=()):
    inst, host = f"{name}.{svc}", "printer-" + str(abs(hash(name)) % 1000) + ".local"
    t = b"".join(bytes([len(x)]) + x.encode() for x in txt) or b"\0"
    return struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 3) + rr(svc, 12, qname(inst)) + \
        rr(inst, 33, struct.pack(">HHH", 0, 0, port) + qname(host)) + rr(inst, 16, t) + rr(host, 1, bytes(map(int, ip.split("."))))


class Bytes(unittest.TestCase):
    def test_status_layout_from_dymos_reference(self):
        st = dymo.parse_status(status_bytes(bay=7, sku="30321", left=42))
        self.assertEqual((st["engine"], st["sku"], st["remaining"], st["low"], st["canPrint"]), ("idle", "30321", 42, True, True))
        st = dymo.parse_status(status_bytes(bay=2, sku="", left=0))
        self.assertEqual((st["canPrint"], st["media"], st["sku"], st["remaining"]), (False, "no labels loaded", "", None))
        self.assertEqual(dymo.parse_status(status_bytes(bay=10))["media"], "the roll isn't a genuine DYMO roll")
        with self.assertRaises(ValueError):
            dymo.parse_status(b"\0" * 3)

    def test_sku_info_and_stock_by_name_or_size(self):
        b = bytearray(63)
        b[0:2] = b"\xb6\xca"
        b[8:20] = b"S0722400".ljust(12, b"\0")
        struct.pack_into("<HH", b, 40, 89, 36)
        info = dymo.parse_sku(bytes(b))
        self.assertEqual((info["sku"], info["widthMm"], info["lengthMm"]), ("S0722400", 36, 89))
        self.assertEqual(dymo.stock_for(info["sku"], info["widthMm"], info["lengthMm"]), "30321")   # by size
        self.assertEqual(dymo.stock_for("30252"), "30252")                                         # by SKU
        self.assertEqual(dymo.stock_for("", 152, 102), "1744907")                                  # either way round
        self.assertEqual(dymo.stock_for("", 54, 101), "")                                          # some other roll
        self.assertIsNone(dymo.parse_sku(b"\0" * 63))

    def test_models_from_bonjour_names(self):
        for text, model in [("DYMO LabelWriter 550 Turbo", "550T"), ("DYMOLW550T1A2B3C", "550T"),
                            ("DYMO LabelWriter 5XL", "5XL"), ("DYMO LabelWriter 550", "550"), ("HP LaserJet 400", "")]:
            self.assertEqual(dymo.model_of(text), model, text)

    def test_announcements_become_printers(self):
        recs = dymo.parse_answers(announcement("DYMO LabelWriter 5XL", "192.0.2.21"))
        recs += dymo.parse_answers(announcement("DYMOLW550T1A2B3C", "192.0.2.20", txt=("ty=DYMO LabelWriter 550 Turbo",)))
        recs += dymo.parse_answers(announcement("Brother HL-2350", "192.0.2.30"))
        recs += dymo.parse_answers(announcement("DYMO LabelWriter 5XL", "192.0.2.21", 631, "_ipp._tcp.local"))
        got = sorted((p["ip"], p["model"], p["port"]) for p in dymo.collect(recs))
        self.assertEqual(got, [("192.0.2.20", "550T", 9100), ("192.0.2.21", "5XL", 9100)])   # raw port, not IPP's 631

    def test_query_packet(self):
        q = dymo.query()
        self.assertEqual(struct.unpack_from(">H", q, 4)[0], len(dymo.SERVICES))
        self.assertIn(b"\x0f_pdl-datastream", q)


class FakeOps:
    def __init__(self, uris=None, alive=(), fail=None):
        self.uris, self.alive, self.fail, self.calls = dict(uris or {}), set(alive), fail, []

    def queue(self, kind):
        return {"tag": "Dymo-550-Turbo", "ship": "Dymo-5XL"}[kind]

    def uri(self, q):
        return self.uris.get(q)

    def add(self, kind, q, ip, port, model):
        if self.fail:
            raise RuntimeError(self.fail)
        self.calls.append(("add", q, ip, model))
        self.uris[q] = f"socket://{ip}:{port}"

    def repoint(self, q, ip, port):
        self.calls.append(("repoint", q, ip))
        self.uris[q] = f"socket://{ip}:{port}"

    def answers(self, ip, port):
        return ip in self.alive

    def busy(self, kind):
        return False


T = {"name": "DYMO LabelWriter 550 Turbo", "model": "550T", "ip": "192.0.2.20", "port": 9100}
X = {"name": "DYMO LabelWriter 5XL", "model": "5XL", "ip": "192.0.2.21", "port": 9100}
X2 = dict(X, ip="192.0.2.22", name="DYMO LabelWriter 5XL (2)")


def auto(ops, found, **kw):
    a = autoprint.Auto(ops, browse=lambda: found, **kw)
    a.scan()
    return a


class Decisions(unittest.TestCase):
    def test_missing_queues_are_added_when_the_printer_is_unambiguous(self):
        ops = FakeOps()
        a = auto(ops, [T, X])
        self.assertEqual(ops.calls, [("add", "Dymo-550-Turbo", "192.0.2.20", "550T"), ("add", "Dymo-5XL", "192.0.2.21", "5XL")])
        self.assertEqual(len(a.since(0)), 2)
        self.assertIn("set it up for shipping labels", a.since(0)[1]["text"])
        self.assertEqual(a.offers, [])

    def test_a_printer_that_moved_is_followed(self):
        ops = FakeOps({"Dymo-5XL": "socket://192.0.2.99:9100", "Dymo-550-Turbo": "socket://192.0.2.20:9100"})
        a = auto(ops, [T, X])
        self.assertEqual(ops.calls, [("repoint", "Dymo-5XL", "192.0.2.21")])
        self.assertIn("moved to 192.0.2.21 (was 192.0.2.99)", a.since(0)[0]["text"])

    def test_a_queue_whose_printer_still_answers_is_left_alone(self):
        ops = FakeOps({"Dymo-5XL": "socket://192.0.2.99:9100", "Dymo-550-Turbo": "socket://192.0.2.20:9100"}, alive={"192.0.2.99"})
        a = auto(ops, [T, X])
        self.assertEqual(ops.calls, [])
        self.assertEqual([(o["ip"], o["why"]) for o in a.offers], [("192.0.2.21", "extra")])   # offered, not used

    def test_two_candidates_are_offered_never_guessed(self):
        ops = FakeOps({"Dymo-550-Turbo": "socket://192.0.2.20:9100"})
        a = auto(ops, [T, X, X2])
        self.assertEqual(ops.calls, [])
        self.assertEqual(sorted((o["ip"], o["kind"], o["why"]) for o in a.offers),
                         [("192.0.2.21", "ship", "add"), ("192.0.2.22", "ship", "add")])

    def test_dnssd_queues_are_cups_business(self):
        ops = FakeOps({"Dymo-550-Turbo": "dnssd://DYMO%20LabelWriter%20550%20Turbo._pdl-datastream._tcp.local/",
                       "Dymo-5XL": "socket://192.0.2.21:9100"})
        self.assertEqual((auto(ops, [T, X]).offers, ops.calls), ([], []))

    def test_windows_only_offers(self):
        ops = FakeOps()
        a = auto(ops, [T, X], can_manage=False)
        self.assertEqual(ops.calls, [])
        self.assertEqual(sorted(o["kind"] for o in a.offers), ["ship", "tag"])

    def test_a_refused_add_is_reported_and_offered(self):
        ops = FakeOps(fail="this user may not change printers")
        a = auto(ops, [X])
        self.assertEqual(a.since(0)[0]["level"], "bad")
        self.assertIn("may not change printers", a.since(0)[0]["text"])
        self.assertEqual([o["why"] for o in a.offers], ["add"])


class Rolls(unittest.TestCase):
    def test_roll_read_once_then_cached_and_never_while_busy(self):
        asked = []
        ops = FakeOps({"Dymo-550-Turbo": "socket://192.0.2.20:9100"})
        a = autoprint.Auto(ops, browse=lambda: [], status=lambda ip, port: asked.append(ip) or dymo.parse_status(status_bytes(sku="30321", left=40)),
                           sku_info=lambda ip, port: {"sku": "30321", "widthMm": 36, "lengthMm": 89})
        r = a.roll("tag", now=1000)
        self.assertEqual((r["stock"], r["remaining"], r["name"]), ("30321", 40, '30321 Large Address (1.4" × 3.5")'))
        a.roll("tag", now=1010)
        self.assertEqual(len(asked), 1)                                     # cached
        ops.busy = lambda kind: True
        self.assertEqual(a.roll("tag", now=2000)["stock"], "30321")         # busy: last known, printer not asked
        self.assertEqual(len(asked), 1)

    def test_unreachable_printer_means_unknown(self):
        def down(ip, port):
            raise OSError("timed out")
        a = autoprint.Auto(FakeOps({"Dymo-5XL": "socket://192.0.2.21:9100"}), browse=lambda: [], status=down)
        self.assertIsNone(a.roll("ship", now=1))


if __name__ == "__main__":
    unittest.main()
