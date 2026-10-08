"""The Windows code paths of the server, run on Linux with a stand-in for winprint (the real one needs Windows + DYMO's
driver; it's tested in the Windows 11 VM). Checks the platform switch: grey pixels to the printer, job states and
plain English, printer status, the browser's barcode check standing in for zbar, and PNG → grey for reprints."""
import base64
import json
import os
import sys
import tempfile
import threading
import types
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

os.environ["LABELDESK_DATA"] = tempfile.mkdtemp()
os.environ["LABELDESK_KEYS"] = "file"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

fake = types.SimpleNamespace(calls=[], jobs={})
def _submit(printer, kind, gray, copies, title):
    fake.calls.append((printer, kind, gray[0], gray[1], len(gray[2]), copies))
    return "41", "30321 Large Address"
fake.submit = _submit
fake.find = lambda: {"tag": "DYMO LabelWriter 550 Turbo", "ship": "DYMO LabelWriter 5XL", "all": []}
fake.job = lambda printer, job_id: fake.jobs.get(job_id, {"state": "done", "message": ""})
fake.cancel = lambda printer, job_id: fake.calls.append(("cancel", job_id))
fake.printer = lambda name: {"state": "idle", "reasons": ["paper out"] if "5XL" in name else [], "message": "", "accepting": True}
sys.modules["winprint"] = fake

import app  # noqa: E402


def png_bytes(w, h, color=(255, 255, 255)):
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes(color + (255,)) * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class WindowsPaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.WINDOWS = True
        app.winprint = fake
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); app.WINDOWS = False  # noqa: E702

    def setUp(self):
        app.RECENT.clear(); fake.calls.clear(); app._found.clear()  # noqa: E702

    def call(self, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_port}/api/{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_grey_pixels_go_to_the_found_dymo_printer(self):
        png = "data:image/png;base64," + base64.b64encode(png_bytes(4, 3)).decode()
        gray = {"w": 4, "h": 3, "data": base64.b64encode(bytes([255] * 12)).decode()}
        code, r = self.call("print", {"kind": "tag", "png": png, "gray": gray, "copies": 2, "fields": {"customer": "Acme"}})
        self.assertEqual((code, r["queue"], r["job"]), (200, "DYMO LabelWriter 550 Turbo", "41"))
        self.assertEqual(fake.calls[0], ("DYMO LabelWriter 550 Turbo", "tag", 4, 3, 12, 2))
        self.assertEqual(self.call("config")[1]["platform"], "windows")

    def test_wrong_grey_size_refused(self):
        png = "data:image/png;base64," + base64.b64encode(png_bytes(4, 3)).decode()
        code, r = self.call("print", {"kind": "tag", "png": png, "gray": {"w": 4, "h": 3, "data": base64.b64encode(b"x").decode()}})
        self.assertEqual(code, 400)

    def test_browser_barcode_check_stands_in_for_zbar(self):
        png = "data:image/png;base64," + base64.b64encode(png_bytes(4, 3)).decode()
        gray = {"w": 4, "h": 3, "data": base64.b64encode(bytes(12)).decode()}
        with mock.patch.object(app.barcode, "available", return_value=False):
            code, r = self.call("print", {"kind": "ship", "png": png, "gray": gray, "check": {"ok": False, "message": "no barcode could be read"}})
            self.assertEqual((code, r["needsForce"]), (422, True))
            code, r = self.call("print", {"kind": "ship", "png": png, "gray": gray, "check": {"ok": True, "carrier": "UPS", "tracking": "1Z9"}})
        self.assertEqual(code, 200)
        self.assertEqual(app.row(r["id"])["tracking"], "1Z9")

    def test_job_states_and_plain_english(self):
        png = "data:image/png;base64," + base64.b64encode(png_bytes(4, 3)).decode()
        gray = {"w": 4, "h": 3, "data": base64.b64encode(bytes(12)).decode()}
        hid = self.call("print", {"kind": "tag", "png": png, "gray": gray, "fields": {"a": 1}})[1]["id"]
        fake.jobs["41"] = {"state": "waiting", "message": "", "flags": ["paper out"]}
        self.assertIn("out of labels", self.call(f"job/{hid}")[1]["message"])
        fake.jobs["41"] = {"state": "failed", "message": "Printer offline", "flags": ["offline", "error"]}
        s = self.call(f"job/{hid}")[1]
        self.assertEqual(s["state"], "failed")
        self.assertIn("offline", s["message"])
        self.assertIn(("cancel", "41"), fake.calls)

    def test_printer_status(self):
        p = self.call("printers")[1]
        self.assertEqual((p["tag"]["ok"], p["ship"]["ok"]), (True, False))
        self.assertIn("out of labels", p["ship"]["status"])


if __name__ == "__main__":
    unittest.main()
