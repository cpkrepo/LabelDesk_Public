"""Server tests — no printer and no CUPS needed (lp / lpstat / pdftoppm are faked where it matters).

    python3 -m unittest discover -s tests
"""
import base64
import hashlib
import json
import os
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
os.environ["LABELDESK_KEYS"] = "file"                                  # never touch the real keyring in tests
os.environ["HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
import app  # noqa: E402
import connectwise  # noqa: E402
import keys  # noqa: E402
sys.path.insert(0, os.path.dirname(__file__))
import fake_connectwise  # noqa: E402

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


class ServerBase(unittest.TestCase):
    """A real LabelDesk server on a free port (no tests here; subclasses add them)."""
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        app.RECENT.clear()                                            # the double-press guard is per label, per 3 s

    def call(self, path, body=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_port}/api/{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)


class Server(ServerBase):
    def test_config_has_both_labels(self):
        code, c = self.call("config")
        self.assertEqual(code, 200)
        self.assertEqual((c["labels"]["tag"]["page"], c["labels"]["ship"]["page"]), ("w79h252", "1744907_4_in_x_6_in"))   # 30252 by default

    def test_print_sends_exact_lp_command_and_remembers(self):
        done = subprocess.CompletedProcess([], 0, "request id is Dymo-550-Turbo-7 (1 file(s))\n", "")
        with mock.patch.object(app.subprocess, "run", return_value=done) as run:
            code, r = self.call("print", {"kind": "tag", "png": PNG, "copies": 3,
                                          "fields": {"customer": "Acme", "received": "2026-09-30", "ticket": "75013"}})
            again = self.call("print", {"kind": "tag", "png": PNG, "copies": 3, "fields": {}})[0]
        self.assertEqual((code, r["job"]), (200, "7"))
        self.assertEqual(again, 409)                                  # same label within 3 s = double press
        args = run.call_args.args[0]
        self.assertEqual(args[:5], ["lp", "-d", "Dymo-550-Turbo", "-n", "3"])
        self.assertIn("PageSize=w79h252", args)
        self.assertIn("ppi=300", args)                               # 1:1 — the canvas is the printable area
        with mock.patch.object(app.ipp, "job", side_effect=LookupError("gone")):     # not this PC's real CUPS
            h = self.call("history")[1]["items"][0]
        self.assertEqual((h["kind"], h["fields"]["ticket"], h["copies"], h["state"]), ("tag", "75013", 3, "sent"))
        self.assertIn("Acme", self.call("customers")[1]["customers"])

    def test_print_error_is_reported_not_remembered(self):
        before = len(self.call("history")[1]["items"])
        fail = subprocess.CompletedProcess([], 1, "", "lp: The printer or class does not exist.")
        ok = {"ok": True, "carrier": "UPS", "tracking": "1Z", "codes": [], "message": ""}
        with mock.patch.object(app.subprocess, "run", return_value=fail), mock.patch.object(app.barcode, "check", return_value=ok):
            code, r = self.call("print", {"kind": "ship", "png": PNG})
        self.assertEqual(code, 502)
        self.assertIn("isn't set up", r["error"])
        h = self.call("history")[1]["items"]
        self.assertEqual((len(h), h[0]["state"]), (before + 1, "failed"))          # recorded as NOT printed

    def test_unreadable_shipping_barcode_needs_force(self):
        bad = {"ok": False, "carrier": None, "tracking": None, "codes": [], "message": "no barcode could be read"}
        with mock.patch.object(app.barcode, "check", return_value=bad), \
                mock.patch.object(app.barcode, "available", return_value=True):      # same result with or without zbar
            code, r = self.call("print", {"kind": "ship", "png": PNG})
        self.assertEqual((code, r["needsForce"]), (422, True))

    def test_job_status_failed_is_cancelled_and_explained(self):
        done = subprocess.CompletedProcess([], 0, "request id is Dymo-550-Turbo-9 (1 file(s))\n", "")
        with mock.patch.object(app.subprocess, "run", return_value=done):
            hid = self.call("print", {"kind": "tag", "png": PNG, "copies": 1, "fields": {"x": 1}})[1]["id"]
        with mock.patch.object(app.ipp, "job", return_value={"state": "stopped", "reasons": [], "message": "Printer is not ready"}), \
                mock.patch.object(app.ipp, "printer", return_value={"state": "idle", "reasons": ["com.dymo.busy-error"], "message": "", "accepting": True}), \
                mock.patch.object(app.subprocess, "run") as run:
            s = self.call(f"job/{hid}")[1]
        self.assertEqual(s["state"], "failed")
        self.assertIn("isn't answering", s["message"])
        self.assertEqual(run.call_args.args[0], ["cancel", "Dymo-550-Turbo-9"])

    def test_history_settles_jobs_nobody_watched(self):
        done = subprocess.CompletedProcess([], 0, "request id is Dymo-550-Turbo-11 (1 file(s))\n", "")
        with mock.patch.object(app.subprocess, "run", return_value=done):
            hid = self.call("print", {"kind": "tag", "png": PNG, "copies": 1, "fields": {"ticket": "80001"}})[1]["id"]
        with mock.patch.object(app.ipp, "job", return_value={"state": "completed", "reasons": [], "message": ""}):
            h = next(r for r in self.call("history")[1]["items"] if r["id"] == hid)
        self.assertEqual(h["state"], "done")                         # the app window closed before it finished

    def test_plain_english(self):
        import ipp
        self.assertIn("out of labels", ipp.plain(["com.dymo.out-of-paper-error"]))
        self.assertIn("genuine DYMO", ipp.plain(["com.dymo.counterfeit-error"]))

    def test_rejects_bad_input_and_cross_site(self):
        self.assertEqual(self.call("print", {"kind": "poster", "png": PNG})[0], 400)
        self.assertEqual(self.call("print", {"kind": "tag", "png": "not a data url"})[0], 400)
        self.assertEqual(self.call("print", {"kind": "tag", "png": PNG}, {"Origin": "http://evil.example"})[0], 403)

    def test_printer_status(self):
        states = [{"state": "idle", "reasons": [], "message": "", "accepting": True}, LookupError("no printer queue")]
        with mock.patch.object(app.ipp, "printer", side_effect=states):
            p = app.printers()
        self.assertEqual((p["tag"]["ok"], p["ship"]["ok"]), (True, False))
        self.assertIn("add-printers", p["ship"]["status"])
        paused = {"state": "stopped", "reasons": ["paused"], "message": "", "accepting": True}
        out = {"state": "idle", "reasons": ["com.dymo.out-of-paper-error"], "message": "", "accepting": True}
        with mock.patch.object(app.ipp, "printer", side_effect=[paused, out]):
            p = app.printers()
        self.assertEqual((p["tag"]["paused"], p["ship"]["ok"]), (True, False))
        self.assertIn("out of labels", p["ship"]["status"])


class ConnectWise(unittest.TestCase):
    """Against tests/fake_connectwise.py — the real API needs the shop's keys."""
    @classmethod
    def setUpClass(cls):
        keys.FILE = os.path.join(tempfile.mkdtemp(), "connectwise.json")
        cls.cw = fake_connectwise.serve()
        threading.Thread(target=cls.cw.serve_forever, daemon=True).start()
        os.environ["LABELDESK_CW_BASE"] = f"http://127.0.0.1:{cls.cw.server_port}/v4_6_release/apis/3.0"
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for s in (cls.cw, cls.srv):
            s.shutdown(); s.server_close()  # noqa: E702

    def setUp(self):
        keys.clear(); connectwise._cache.clear(); app._cw_check.clear()  # noqa: E702

    call = Server.call

    def save(self, **kw):
        return self.call("cw/settings", {"company": "shop", "public": "pub", "private": "priv", "client_id": "client", **kw})

    def test_not_configured_says_so(self):
        self.assertFalse(self.call("cw/status")[1]["configured"])
        code, r = self.call("cw/ticket/75013")
        self.assertEqual(code, 502)
        self.assertIn("Settings", r["error"])

    def test_off_by_default_and_never_calls_out_without_keys(self):
        with mock.patch.object(connectwise, "_get", side_effect=AssertionError("network!")) as net:
            st = self.call("cw/status")[1]
        self.assertEqual((st["on"], st["configured"]), (False, False))
        net.assert_not_called()                                       # no keys → LabelDesk never contacts anything

    def test_on_only_when_keys_work(self):
        self.assertTrue(self.save()[1]["on"])
        self.save(private="wrong")                                    # fake answers 401
        st = self.call("cw/status")[1]
        self.assertEqual((st["on"], st["configured"], st["working"]), (False, True, False))
        self.assertTrue(st["problem"])

    def test_settings_saved_privately_and_never_echoed(self):
        code, r = self.save(private="S3CRET-private-KEY")
        self.assertEqual((code, r["configured"], r["company"]), (200, True, "shop"))
        self.assertNotIn("S3CRET", json.dumps(r) + json.dumps(self.call("cw/status")[1]))   # private key never comes back
        self.assertEqual(oct(os.stat(keys.FILE).st_mode & 0o777), "0o600")
        self.call("cw/settings", {"company": "shop", "public": "pub", "private": "", "client_id": "client"})
        self.assertEqual(keys.load()["private"], "S3CRET-private-KEY")   # blank private key = keep the stored one

    def test_connection_test(self):
        self.save()
        r = self.call("cw/test", {})[1]
        self.assertEqual((r["ok"], r["version"]), (True, "v2025.1.12345"))
        self.save(private="wrong")
        code, r = self.call("cw/test", {})
        self.assertEqual(code, 502)
        self.assertIn("rejected the API keys", r["error"])

    def test_ticket_lookup(self):
        self.save()
        r = self.call("cw/ticket/75013")[1]
        self.assertEqual((r["company"], r["contact"], r["summary"], r["status"]), ("Acme Dental Group", "Jane Smith", "Laptop won't boot", "In Progress"))
        self.assertEqual(self.call("cw/ticket/75020")[1]["contact"], "Bob Jones")        # contactName fallback
        self.assertEqual(self.call("cw/ticket/81000")[1]["kind"], "project")             # project ticket
        code, r = self.call("cw/ticket/99999")
        self.assertEqual((code, r["error"]), (404, "no ticket #99999 in ConnectWise"))

    def test_configurations(self):
        self.save()
        items = self.call("cw/configurations?company=101&ticket=75013")[1]["items"]
        self.assertEqual([(c["name"], c["onTicket"]) for c in items], [("ACME-LT-07", True), ("ACME-FRONT-01", False)])
        code, r = self.call("cw/configurations?company=250")
        self.assertEqual(code, 502)
        self.assertIn("Inquire", r["error"])                           # permission problem explained, and who fixes it


if __name__ == "__main__":
    unittest.main()


class UpdateCheck(unittest.TestCase):
    """After each print the browser asks /api/update; the server asks GitHub's VERSION (here: a local stand-in)."""
    def serve(self, body, status=200):
        from http.server import BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(status); self.end_headers(); self.wfile.write(body.encode())

            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close); self.addCleanup(srv.shutdown)
        app._update.update(at=0, result=None)
        return {"update_check": True, "update_url": f"http://127.0.0.1:{srv.server_port}/VERSION"}

    def test_version_compare_is_numeric(self):
        self.assertGreater(app.version_tuple("0.6.10"), app.version_tuple("0.6.9"))
        self.assertEqual(app.version_tuple("not a version"), ())

    def test_newer_version_on_github(self):
        with mock.patch.object(app, "VERSION", "0.6.0"):
            r = app.check_update(self.serve("0.6.1\n"))
        self.assertEqual((r["latest"], r["newer"], r["error"]), ("0.6.1", True, None))

    def test_same_or_older_is_not_newer(self):
        with mock.patch.object(app, "VERSION", "0.6.1"):
            self.assertFalse(app.check_update(self.serve("0.6.0"))["newer"])

    def test_unreachable_or_garbage_never_says_newer(self):
        cfg = self.serve("<html>Not Found</html>", 404)
        self.assertFalse(app.check_update(cfg)["newer"])
        app._update.update(at=0, result=None)
        r = app.check_update(self.serve("<html>login</html>"))
        self.assertEqual((r["newer"], r["error"] is not None), (False, True))

    def test_off_means_no_request(self):
        with mock.patch.object(app.urllib.request, "urlopen") as op:
            r = app.check_update({"update_check": False})
        op.assert_not_called()
        self.assertEqual((r["enabled"], r["newer"]), (False, False))

    def test_cached_for_a_batch(self):
        cfg = self.serve("0.9.0")
        app.check_update(cfg, now=1000)
        with mock.patch.object(app.urllib.request, "urlopen") as op:
            app.check_update(cfg, now=1030)
        op.assert_not_called()


class LogoAndUpdateNow(ServerBase):
    """Per-PC logo (Settings → Tag logo) and the in-app update buttons' guard rails."""
    LOGO = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 40).decode()

    def setUp(self):
        super().setUp()
        self.addCleanup(lambda: os.path.exists(app.logo_path()) and os.remove(app.logo_path()))

    def get_raw(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.srv.server_port}/api/{path}", timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_logo_save_serve_clear(self):
        self.assertEqual(self.get_raw("logo")[0], 404)                           # none yet: tag drawn without one
        self.assertEqual(self.call("logo", {"png": self.LOGO})[0], 200)
        code, raw = self.get_raw("logo")
        self.assertEqual((code, raw[:4]), (200, b"\x89PNG"))
        self.assertTrue(app.logo_path().startswith(app.CONF_DIR))               # per PC, not in the app folder
        self.assertEqual(self.call("logo/clear", {})[0], 200)
        self.assertEqual(self.get_raw("logo")[0], 404)

    def test_logo_must_be_an_image(self):
        bad = "data:image/png;base64," + base64.b64encode(b"<svg onload=x>").decode()
        self.assertEqual(self.call("logo", {"png": bad})[0], 400)
        self.assertEqual(self.call("logo", {"png": "data:text/html;base64,PGI+"})[0], 400)

    def test_old_logo_in_the_app_folder_moves_to_config(self):
        with tempfile.TemporaryDirectory() as web:
            with open(os.path.join(web, "tag-logo.png"), "wb") as f:
                f.write(b"\x89PNGold")
            with mock.patch.object(app, "WEB", web):
                app.migrate_logo()
            with open(app.logo_path(), "rb") as f:
                self.assertEqual(f.read(), b"\x89PNGold")

    def test_update_now_refuses_local_changes(self):
        with mock.patch.object(app, "git_state", return_value={"dirty": True, "ahead": 0}):
            code, r = self.call("update/run", {})
        self.assertEqual(code, 400)
        self.assertIn("tools/update.sh", r["error"])
        with mock.patch.object(app, "git_state", return_value={"dirty": False, "ahead": 2}):
            self.assertEqual(self.call("update/run", {})[0], 400)

    def test_update_now_runs_outside_the_service(self):
        with mock.patch.object(app, "git_state", return_value={"dirty": False, "ahead": 0}), \
                mock.patch.object(app.shutil, "which", return_value="/usr/bin/systemd-run"), \
                mock.patch.object(app.subprocess, "run") as run:
            self.assertEqual(self.call("update/run", {})[0], 200)
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[:3], ["systemd-run", "--user", "--collect"])
        self.assertIn("tools/update.sh", cmd[-1])

    def test_update_now_needs_a_git_checkout(self):
        with mock.patch.object(app, "git_state", return_value=None):
            self.assertEqual(self.call("update/run", {})[0], 400)

    def test_windows_only_actions_refused_on_linux(self):
        for path, body in (("update/install", {"version": "9.9.9"}), ("windows/printer-check", {"ips": ["192.0.2.1"]}),
                           ("windows/add-dymo", {"model": "550", "ip": "192.0.2.1"})):
            self.assertEqual(self.call(path, body)[0], 400, path)

    def test_printer_ips_are_validated(self):
        with self.assertRaises(ValueError):
            app.check_ips(["192.0.2.1; Remove-Item C:\\"])
        self.assertEqual(app.check_ips([" 192.0.2.1 "]), ["192.0.2.1"])


class WindowsInstallUpdate(unittest.TestCase):
    """Install update (Windows): only a newer version, only the release's MSI, only if its .sha256 matches."""
    def fake_downloads(self, msi, sha):
        rel = json.dumps({"assets": [{"name": "LabelDesk-9.9.9.msi", "browser_download_url": "https://x/msi"},
                                     {"name": "LabelDesk-9.9.9.msi.sha256", "browser_download_url": "https://x/sha"}]}).encode()
        return lambda url, limit, accept=None: {"https://x/msi": msi, "https://x/sha": sha}.get(url, rel)

    def run_install(self, msi, sha, version="9.9.9"):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(app, "WINDOWS", True), \
                mock.patch.object(app, "DATA", d), mock.patch.object(app, "download", self.fake_downloads(msi, sha)), \
                mock.patch.object(app.subprocess, "Popen") as popen, mock.patch.object(app.threading, "Timer") as timer:
            app.install_windows_update(version)
            with open(os.path.join(d, "update", "install-update.ps1"), encoding="utf-8") as f:
                return popen, timer, f.read()

    def test_good_checksum_installs_and_restarts(self):
        msi = b"MSI bytes"
        popen, timer, script = self.run_install(msi, (hashlib.sha256(msi).hexdigest() + "  LabelDesk-9.9.9.msi\n").encode())
        self.assertIn("powershell.exe", popen.call_args[0][0])
        self.assertIn("msiexec.exe", script)
        self.assertIn("/qb", script)
        self.assertIn("Wait-Process -Id", script)                               # waits for this server to let go of its files
        self.assertIn("labeldesk-server.pyw", script)                           # and starts it again afterwards
        timer.assert_called_once()

    def test_bad_checksum_installs_nothing(self):
        with self.assertRaises(RuntimeError):
            self.run_install(b"tampered", b"0" * 64)

    def test_not_newer_is_refused(self):
        with mock.patch.object(app, "WINDOWS", True), self.assertRaises(ValueError):
            app.install_windows_update(app.VERSION)


class WindowsOlderVersion(WindowsInstallUpdate):
    """Settings → Version on Windows: an OLDER version uninstalls the current one first (an older MSI won't replace it)."""
    def test_older_version_uninstalls_first(self):
        msi = b"old MSI"
        sha = (hashlib.sha256(msi).hexdigest() + "\n").encode()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(app, "WINDOWS", True), mock.patch.object(app, "VERSION", "9.9.10"), \
                mock.patch.object(app, "DATA", d), mock.patch.object(app, "download", self.fake_downloads(msi, sha)), \
                mock.patch.object(app.subprocess, "Popen"), mock.patch.object(app.threading, "Timer"):
            app.install_windows_version("9.9.9")
            with open(os.path.join(d, "update", "install-update.ps1"), encoding="utf-8") as f:
                script = f.read()
        self.assertLess(script.index("'/x'"), script.index("'/i'"))           # uninstall, then install the older one
        self.assertIn("RelatedProducts('{6B9C2E31-4A57-4D3F-9E1B-2F7C5A0D8E41}')", script)

    def test_newer_version_does_not_uninstall(self):
        msi = b"MSI bytes"
        _, _, script = self.run_install(msi, (hashlib.sha256(msi).hexdigest() + "\n").encode())
        self.assertNotIn("'/x'", script)


class Versions(ServerBase):
    """Settings → Version: the list from GitHub's releases, switching this PC (held there), and the owner-only 'every PC'."""
    RELEASES = json.dumps([
        {"tag_name": "v0.9.0", "published_at": "2026-10-10T12:00:00Z", "body": "- **Printers** set themselves up\n- Rolls\n\n---\nfooter",
         "assets": [{"name": "LabelDesk-0.9.0.msi"}, {"name": "LabelDesk-0.9.0.msi.sha256"}]},
        {"tag_name": "v0.7.2", "published_at": "2026-10-10T10:00:00Z", "body": "- Rollback", "assets": []},
        {"tag_name": "v0.8.1", "published_at": "2026-10-10T11:00:00Z", "body": "", "draft": False, "assets": []},
        {"tag_name": "not-a-version", "assets": []}]).encode()

    def setUp(self):
        super().setUp()
        app._versions.update(at=0, list=None)

    def test_list_is_newest_first_with_notes(self):
        with mock.patch.object(app, "download", return_value=self.RELEASES), mock.patch.object(app, "is_publisher", return_value=False):
            code, v = self.call("versions")
        self.assertEqual(code, 200)
        self.assertEqual([x["version"] for x in v["versions"]], ["0.9.0", "0.8.1", "0.7.2"])
        self.assertEqual(v["versions"][0]["notes"], ["**Printers** set themselves up", "Rolls"])
        self.assertEqual((v["newest"], v["publisher"], v["versions"][0]["msi"], v["versions"][1]["msi"]), ("0.9.0", False, True, False))

    def test_offline_says_so(self):
        with mock.patch.object(app, "download", side_effect=OSError("no network")), mock.patch.object(app, "is_publisher", return_value=False):
            v = self.call("versions")[1]
        self.assertIn("couldn't reach GitHub", v["error"])

    def test_switching_runs_the_tool_outside_labeldesk(self):
        with mock.patch.object(app, "git_state", return_value={"dirty": False, "ahead": 0}), \
                mock.patch.object(app, "run_detached") as run:
            self.assertEqual(self.call("version/use", {"version": "0.8.1"})[0], 200)
            self.assertEqual(self.call("version/use", {"version": "newest"})[0], 200)
        self.assertEqual([c.args[0] for c in run.call_args_list], ["tools/switch-version.sh 0.8.1", "tools/switch-version.sh newest"])

    def test_every_pc_is_owner_only_and_local_work_is_never_lost(self):
        with mock.patch.object(app, "git_state", return_value={"dirty": False, "ahead": 0}), \
                mock.patch.object(app, "run_detached") as run, mock.patch.object(app, "is_publisher", return_value=False):
            code, r = self.call("version/use", {"version": "0.8.1", "everyone": True})
        self.assertEqual((code, run.called), (400, False))
        self.assertIn("only the owner", r["error"])
        with mock.patch.object(app, "git_state", return_value={"dirty": True, "ahead": 0}), mock.patch.object(app, "run_detached") as run:
            self.assertEqual(self.call("version/use", {"version": "0.8.1"})[0], 400)
        self.assertFalse(run.called)
        self.assertEqual(self.call("version/use", {"version": "0.8.1; rm -rf ~"})[0], 400)

    def test_a_held_pc_gets_no_update_notice(self):
        with mock.patch.object(app, "config", return_value={**app.config(), "hold_version": "0.8.1"}):
            u = app.check_update()
        self.assertEqual((u["held"], u["newer"]), ("0.8.1", False))


class TagLabelSetting(ServerBase):
    """Settings → Tag labels: 30252 Address (the shop's roll, default) or 30321 Large Address; saved in config.json."""
    def tearDown(self):
        app.save_config(tag_label=app.DEFAULT_TAG_STOCK)

    def test_default_is_30252_with_the_ppd_area(self):
        t = self.call("config")[1]["labels"]["tag"]
        self.assertEqual((t["page"], t["stock"]), ("w79h252", "30252 Address"))
        w = int((t["safe_in"][2] - t["safe_in"][0]) * 300) - 1
        h = int((t["safe_in"][3] - t["safe_in"][1]) * 300) - 1
        self.assertEqual((w, h), (298, 962))                                   # the canvas the browser draws

    def test_switching_to_30321_changes_the_page_lp_gets(self):
        self.assertEqual(self.call("settings/tag-label", {"label": "30321"})[0], 200)
        self.assertEqual(self.call("config")[1]["labels"]["tag"]["page"], "w102h252")
        done = subprocess.CompletedProcess([], 0, "request id is Dymo-550-Turbo-8 (1 file(s))\n", "")
        with mock.patch.object(app.subprocess, "run", return_value=done) as run:
            self.call("print", {"kind": "tag", "png": PNG, "copies": 1, "fields": {"x": 2}})
        self.assertIn("PageSize=w102h252", run.call_args[0][0])

    def test_unknown_label_refused_and_other_settings_kept(self):
        app.save_config(flip_tag=True)
        self.assertEqual(self.call("settings/tag-label", {"label": "99999"})[0], 400)
        self.call("settings/tag-label", {"label": "30252"})
        self.assertTrue(app.config()["flip_tag"])
        app.save_config(flip_tag=False)
