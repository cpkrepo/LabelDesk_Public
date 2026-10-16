"""Windows failure points from the 2026-10-16 shakedown (docs/dev/windows.md), checked on Linux with stand-ins; the
Windows 11 VM checks the real thing. Printer choice when a re-added printer leaves a stale "(Copy 1)", finding a
renamed / re-added printer without a restart, a printer whose address stopped answering, a version hold left behind by
a hand install, and the update helper's script for user names like José O'Brien."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

os.environ["LABELDESK_AUTO_PRINTERS"] = "0"
os.environ.setdefault("LABELDESK_DATA", tempfile.mkdtemp())
os.environ.setdefault("LABELDESK_KEYS", "file")
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "server"))

import app  # noqa: E402

# the real winprint module under its own name (test_windows_paths swaps sys.modules["winprint"] for a stand-in)
_spec = importlib.util.spec_from_file_location("winprint_real", os.path.join(HERE, "..", "server", "winprint.py"))
winprint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(winprint)

T550, T5XL = "dymo labelwriter 550 turbo", "dymo labelwriter 5xl"


class PickPrinters(unittest.TestCase):
    def test_renamed_printers_are_found_by_driver(self):
        got = winprint.pick_printers([("Asset Tags", T550, 0, 0), ("Shipping Labels", T5XL, 0, 0), ("Office", "hp", 0, 0)])
        self.assertEqual((got["tag"], got["ship"]), ("Asset Tags", "Shipping Labels"))

    def test_offline_original_loses_to_its_working_copy(self):
        got = winprint.pick_printers([("DYMO LabelWriter 550 Turbo", T550, 0x80, 0),
                                      ("DYMO LabelWriter 550 Turbo (Copy 1)", T550, 0, 0)])
        self.assertEqual(got["tag"], "DYMO LabelWriter 550 Turbo (Copy 1)")

    def test_the_copy_that_answers_wins_even_when_windows_says_both_are_fine(self):
        ps = [("DYMO LabelWriter 550 Turbo", T550, 0, 0), ("DYMO LabelWriter 550 Turbo (Copy 1)", T550, 0, 0)]
        asked = []
        got = winprint.pick_printers(ps, lambda n: asked.append(n) or "(Copy" in n)
        self.assertEqual(got["tag"], "DYMO LabelWriter 550 Turbo (Copy 1)")
        self.assertEqual(len(asked), 2)

    def test_no_network_probe_without_a_choice(self):
        asked = []
        winprint.pick_printers([("DYMO LabelWriter 550 Turbo", T550, 0, 0)], lambda n: asked.append(n))
        self.assertEqual(asked, [])

    def test_unknown_reachability_keeps_the_original(self):
        got = winprint.pick_printers([("DYMO LabelWriter 550 Turbo", T550, 0, 0),
                                      ("DYMO LabelWriter 550 Turbo (Copy 1)", T550, 0, 0)], lambda n: None)
        self.assertEqual(got["tag"], "DYMO LabelWriter 550 Turbo")


class FindAgain(unittest.TestCase):
    def setUp(self):
        self.win = app.WINDOWS
        self.names = {"tag": "DYMO LabelWriter 550 Turbo", "ship": "DYMO LabelWriter 5XL"}
        self.sent = []

        def submit(printer, kind, gray, copies=1, title="", paper=None):
            if printer not in self.names.values():
                raise RuntimeError(f"opening printer {printer!r} failed (Windows error 1801)")
            self.sent.append((printer, copies))
            return "7", "30252"
        self.stub = types.SimpleNamespace(find=lambda: dict(self.names, all=list(self.names.values())), submit=submit)
        self.patches = [mock.patch.object(app, "winprint", self.stub, create=True), mock.patch.object(app, "WINDOWS", True),
                        mock.patch.object(app, "config", lambda: {"tag_label": "30252"})]
        for p in self.patches:
            p.start()
        app._found.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        app._found.clear()

    def test_found_again_after_the_ttl_and_on_refresh(self):
        self.assertEqual(app.queue_for("tag"), "DYMO LabelWriter 550 Turbo")
        self.names["tag"] = "DYMO LabelWriter 550 Turbo (Copy 1)"
        self.assertEqual(app.queue_for("tag"), "DYMO LabelWriter 550 Turbo")          # cached
        self.assertEqual(app.queue_for("tag", refresh=True), "DYMO LabelWriter 550 Turbo (Copy 1)")
        self.names["tag"] = "Asset Tags"
        app._found["at"] -= app.FIND_TTL_S + 1
        self.assertEqual(app.queue_for("tag"), "Asset Tags")

    def test_print_to_a_deleted_printer_goes_to_its_replacement(self):
        app.queue_for("tag")
        self.names["tag"] = "DYMO LabelWriter 550 Turbo (Copy 1)"                      # deleted + re-added
        with mock.patch.object(app, "labels", lambda cfg=None: app.LABELS):
            q, job = app.submit("tag", b"", 3, gray=(2, 2, b"\0" * 4))
        self.assertEqual((q, job, self.sent), ("DYMO LabelWriter 550 Turbo (Copy 1)", "7",
                                                [("DYMO LabelWriter 550 Turbo (Copy 1)", 3)]))

    def test_spooler_down_keeps_what_was_found(self):
        app.queue_for("tag")
        self.stub.find = mock.Mock(side_effect=RuntimeError("EnumPrinters failed (Windows error 1722)"))
        self.assertEqual(app.queue_for("tag", refresh=True), "DYMO LabelWriter 550 Turbo")


class NotAnswering(unittest.TestCase):
    def setUp(self):
        app._answer.clear()
        self.ops = types.SimpleNamespace(uri=lambda q: "socket://192.0.2.50:9100", busy=lambda k: False,
                                         answers=lambda ip, port: False)

    def check(self, offers=()):
        with mock.patch.object(app.AUTO, "ops", self.ops), mock.patch.object(app.AUTO, "offers", list(offers)), \
                mock.patch.object(app, "config", lambda: {"auto_printers": True}), \
                mock.patch.object(app, "queue_for", lambda kind, refresh=False: "DYMO LabelWriter 550 Turbo"):
            return app.not_answering("tag", now=1000.0)

    def test_dead_address_is_said_plainly(self):
        self.assertIn("not answering at 192.0.2.50", self.check())

    def test_new_address_found_on_the_network_is_named(self):
        text = self.check([{"kind": "tag", "why": "moved", "ip": "192.0.2.77"}])
        self.assertIn("found it at 192.0.2.77", text)

    def test_quiet_when_it_answers_is_busy_or_has_no_address(self):
        self.ops.answers = lambda ip, port: True
        self.assertEqual(self.check(), "")
        app._answer.clear()
        self.ops.answers, self.ops.busy = (lambda ip, port: False), (lambda k: True)
        self.assertEqual(self.check(), "")
        app._answer.clear()
        self.ops.busy, self.ops.uri = (lambda k: False), (lambda q: "windows:DYMO LabelWriter 550 Turbo")
        self.assertEqual(self.check(), "")

    def test_off_when_network_checks_are_off(self):
        with mock.patch.object(app, "config", lambda: {"auto_printers": False}):
            self.assertEqual(app.not_answering("tag", now=1000.0), "")


class VersionHold(unittest.TestCase):
    def test_hold_from_before_a_hand_install_is_dropped_at_start(self):
        with mock.patch.object(app, "save_config") as save:
            app.stale_hold({"hold_version": "0.0.1"})
        save.assert_called_once_with(hold_version=None)

    def test_hold_on_the_running_version_stays(self):
        with mock.patch.object(app, "save_config") as save:
            app.stale_hold({"hold_version": app.VERSION})
            app.stale_hold({})
        save.assert_not_called()


class UpdateHelper(unittest.TestCase):
    def test_paths_with_apostrophes_and_accents_stay_one_quoted_string(self):
        base = "C:\\Users\\José O'Brien\\AppData\\Local"
        s = app.update_script(42, base + "\\LabelDesk\\update\\LabelDesk-1.0.0.msi", base + "\\LabelDesk\\update\\install.log",
                              base + "\\Programs\\LabelDesk\\python\\pythonw.exe",
                              base + "\\Programs\\LabelDesk\\labeldesk-server.pyw", older=False)
        self.assertNotIn("O'Brien", s)                                   # every ' doubled inside '…'
        self.assertEqual(s.count("José O''Brien"), 4)
        self.assertEqual(s.replace("''", "").count("'") % 2, 0)          # quotes balance
        self.assertNotIn("RelatedProducts", s)                           # newer: no uninstall first
        self.assertIn("RelatedProducts", app.update_script(42, "a.msi", "l", "p", "s", older=True))

    def test_psq(self):
        self.assertEqual(app.psq("it's"), "'it''s'")


if __name__ == "__main__":
    unittest.main()
