"""The macOS code paths of the server, run anywhere: the grey pixels become an exact-size PDF for lp (checked here
byte-wise; the full print through DYMO's Mac driver runs in CI on a real Mac: .github/workflows/macos.yml), Update now
without systemd, and the Keychain for the ConnectWise keys (the secret never on a command line)."""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

os.environ["LABELDESK_AUTO_PRINTERS"] = "0"                    # no printer polling in tests
os.environ["LABELDESK_DATA"] = tempfile.mkdtemp()
os.environ["LABELDESK_KEYS"] = "file"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

import app  # noqa: E402
import keys  # noqa: E402
from test_windows_paths import png_bytes  # noqa: E402


def pdf_parts(pdf):
    page = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", pdf)
    img = re.search(rb"/Width (\d+) /Height (\d+) /ColorSpace /DeviceGray", pdf)
    cm = re.search(rb"q ([\d.]+) 0 0 ([\d.]+) ([\d.]+) ([\d.]+) cm /Im0 Do Q", pdf)
    return ([float(x) for x in page.groups()], [int(x) for x in img.groups()], [float(x) for x in cm.groups()])


class MacPaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.MAC = True
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); app.MAC = False  # noqa: E702

    def setUp(self):
        app.RECENT.clear()

    def call(self, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_port}/api/{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_grey_pixels_print_as_an_exact_size_pdf(self):
        sent = {}

        def run(args, **kw):
            with open(args[-1], "rb") as f:                         # lp's temp file is deleted right after
                sent["pdf"], sent["args"] = f.read(), args
            return subprocess.CompletedProcess(args, 0, "request id is Dymo-550-Turbo-12 (1 file(s))\n", "")
        png = "data:image/png;base64," + base64.b64encode(png_bytes(298, 962)).decode()
        gray = {"w": 298, "h": 962, "data": base64.b64encode(bytes([255] * 298 * 962)).decode()}
        with mock.patch.object(app.subprocess, "run", side_effect=run):
            code, r = self.call("print", {"kind": "tag", "png": png, "gray": gray, "copies": 1, "fields": {}})
        self.assertEqual((code, r["job"]), (200, "12"))
        args = sent["args"]
        self.assertEqual(args[:3], ["lp", "-d", "Dymo-550-Turbo"])
        self.assertIn("PageSize=w79h252", args)
        self.assertNotIn("ppi=300", args)                           # the PDF carries the size; no image options
        self.assertTrue(args[-1].endswith(".pdf") and sent["pdf"].startswith(b"%PDF-1.4"))
        page, img, (iw, ih, x, y) = pdf_parts(sent["pdf"])
        self.assertEqual((page, img), ([79, 252], [298, 962]))
        self.assertAlmostEqual(iw, 298 * 72 / 300, places=2)        # 300 dpi, 1:1
        self.assertAlmostEqual(ih, 962 * 72 / 300, places=2)
        left, bottom, right, top = (v * 72 for v in app.labels()["tag"]["safe_in"])
        self.assertAlmostEqual(x + iw / 2, (left + right) / 2, places=2)   # centred in the printable area
        self.assertAlmostEqual(y + ih / 2, (bottom + top) / 2, places=2)
        self.assertEqual(self.call("config")[1]["platform"], "mac")

    def test_pdf_xref_offsets_point_at_the_objects(self):
        pdf = app.label_pdf(app.labels()["ship"], 1199, 1799, bytes(1199 * 1799))
        self.assertEqual(pdf_parts(pdf)[:2], ([296, 452], [1199, 1799]))
        xref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
        offsets = [int(l[:10]) for l in pdf[xref:].split(b"\n")[3:8]]
        for n, off in enumerate(offsets, 1):
            self.assertTrue(pdf[off:].startswith(f"{n} 0 obj".encode()), n)

    def test_without_grey_pixels_it_falls_back_to_the_png(self):
        done = subprocess.CompletedProcess([], 0, "request id is Dymo-5XL-3 (1 file(s))\n", "")
        png = "data:image/png;base64," + base64.b64encode(png_bytes(4, 3)).decode()
        with mock.patch.object(app.subprocess, "run", return_value=done) as run, \
                mock.patch.object(app.barcode, "available", return_value=False):
            code, _ = self.call("print", {"kind": "ship", "png": png, "copies": 1, "fields": {}, "check": {"ok": True}})
        self.assertEqual(code, 200)
        self.assertIn("ppi=300", run.call_args.args[0])

    def test_update_now_runs_detached_without_systemd(self):
        with mock.patch.object(app, "git_state", return_value={"dirty": False, "ahead": 0}), \
                mock.patch.object(app.subprocess, "Popen") as popen, mock.patch.object(app.shutil, "which", return_value=None):
            app.run_update_now()
            res = app.check_update({"update_check": False})
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertIn("tools/update.sh", popen.call_args.args[0][-1])
        if res["how"] == "git":
            self.assertTrue(res["canUpdateNow"])


class Keychain(unittest.TestCase):
    def test_secret_goes_to_security_on_stdin_only(self):
        calls = []
        stored = {}

        def run(args, input=None, **kw):
            calls.append((args, input))
            if args[:2] == ["security", "-i"]:
                stored["b64"] = input.split(" -w ")[1].strip()
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1] == "find-generic-password":
                return subprocess.CompletedProcess(args, 0, stored.get("b64", "") + "\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")
        creds = {"company": "acme", "public": "pub", "private": "s3cret", "client_id": "cid"}
        with mock.patch.dict(os.environ, {"LABELDESK_KEYS": "keychain"}), mock.patch.object(keys.subprocess, "run", side_effect=run):
            self.assertEqual(keys.save(creds), "Mac Keychain")
            self.assertEqual(keys.load(), creds)
            keys.clear()
        for args, _ in calls:
            self.assertFalse(any("s3cret" in a or stored["b64"] in a for a in args), args)
        self.assertEqual(calls[-1][0][:2], ["security", "delete-generic-password"])


if __name__ == "__main__":
    unittest.main()
