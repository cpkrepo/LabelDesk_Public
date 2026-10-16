"""The Windows installer's upgrade rules (windows/labeldesk.wxs) and the server's single-copy start — the parts that let a
new .msi replace a running older LabelDesk without an uninstall (tested end to end on the Windows 11 VM 2026-10-16,
docs/dev/windows.md). Checks the source here; the VM checks the real thing."""
import base64
import os
import socket
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

os.environ["LABELDESK_AUTO_PRINTERS"] = "0"
os.environ.setdefault("LABELDESK_DATA", tempfile.mkdtemp())
os.environ.setdefault("LABELDESK_KEYS", "file")
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "server"))
NS = {"w": "http://schemas.microsoft.com/wix/2006/wi"}


class MsiUpgrade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = ET.parse(os.path.join(ROOT, "windows", "labeldesk.wxs")).getroot().find("w:Product", NS)
        cls.seq = {}
        for el in cls.product.find("w:InstallExecuteSequence", NS):
            name = el.get("Action") or el.tag.split("}")[1]
            cls.seq[name] = (int(el.get("Sequence") or 0), (el.text or "").strip())
        cls.ca = {c.get("Id"): c for c in cls.product.findall("w:CustomAction", NS)}

    def test_running_server_is_stopped_before_the_files_in_use_check(self):
        # InstallValidate (1400) is where Windows asks to close "Python" — the server must be gone by then
        self.assertLess(self.seq["SetPowerShell"][0], self.seq["StopLabelDesk"][0])
        self.assertTrue(1000 < self.seq["StopLabelDesk"][0] < 1400)
        self.assertEqual(self.seq["RemoveExistingProducts"][0], 1401)       # explicit: wixl's After= moved it
        self.assertEqual(self.ca["StopLabelDesk"].get("Return"), "ignore")  # nothing running is fine

    def test_stop_command_targets_only_labeldesk_python(self):
        cmd = self.ca["StopLabelDesk"].get("ExeCommand")
        self.assertNotRegex(cmd, r"[\[\]]")                                 # MSI would read [..] as properties
        ps = base64.b64decode(cmd.split("-EncodedCommand ")[1]).decode("utf-16-le")
        self.assertIn(r"*\Programs\LabelDesk\python\python*.exe", ps)
        self.assertIn("Stop-Process", ps)

    def test_new_server_started_after_install_not_after_uninstall(self):
        n, cond = self.seq["StartLabelDesk"]
        self.assertGreater(n, 6600)                                          # after InstallFinalize
        self.assertEqual(cond, 'NOT (REMOVE~="ALL")')
        self.assertEqual(self.ca["StartLabelDesk"].get("Return"), "asyncNoWait")
        self.assertIn("labeldesk-server.pyw", self.ca["StartLabelDesk"].get("ExeCommand"))


class SingleCopy(unittest.TestCase):
    def test_second_server_on_the_same_port_exits_before_watching_the_inbox(self):
        import app
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        started = []
        orig_cfg, orig_inbox = app.config, app.Inbox
        app.config = lambda: {**orig_cfg(), "bind": "127.0.0.1", "port": port}
        app.Inbox = lambda dirs: started.append(dirs)
        try:
            app.main()                                                       # returns instead of serving
        finally:
            app.config, app.Inbox = orig_cfg, orig_inbox
            s.close()
        self.assertEqual(started, [])

    def test_windows_binds_exclusively(self):
        import app
        self.assertEqual(app.Server.allow_reuse_address, not app.WINDOWS)


if __name__ == "__main__":
    unittest.main()
