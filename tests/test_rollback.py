"""tools/rollback.sh against a throwaway "GitHub" (a bare repo) and two PCs (clones) — no network, no app install.

    python3 -m unittest tests.test_rollback
"""
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_update import HERE, Update, sh  # noqa: E402

ROLLBACK = os.path.join(HERE, "..", "tools", "rollback.sh")


@unittest.skipUnless(shutil.which("git"), "needs git")
class Rollback(Update):
    def setUp(self):
        super().setUp()                                           # hub has 0.6.0; PCs a and b are clones of it
        for d in (self.a, self.b):
            shutil.copy(ROLLBACK, os.path.join(d, "tools", "rollback.sh"))
        sh(self.a, "git", "add", "tools/rollback.sh"); sh(self.a, "git", "commit", "-qm", "add rollback")
        sh(self.a, "git", "tag", "v0.6.0"); sh(self.a, "git", "push", "-q", "origin", "main", "v0.6.0")
        sh(self.b, "git", "checkout", "-q", "--", "."); sh(self.b, "git", "clean", "-qfd"); sh(self.b, "git", "pull", "-q")
        # a "bad" 0.6.1: changes app.py and adds a file
        self.write(self.a, "app.py", "A = 'bad'\nB = 1\n")
        self.write(self.a, "extra.py", "X = 1\n")
        self.assertEqual(self.update(self.a).returncode, 0)
        self.assertEqual(self.hub_version(), "0.6.1")

    def rollback(self, d, *args):
        return sh(d, "bash", "tools/rollback.sh", *args, check=False)

    def hub_file(self, rel):
        return sh(self.tmp, "git", "--git-dir", self.hub, "show", f"main:{rel}", check=False)

    def test_lists_versions(self):
        r = self.rollback(self.b)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0.6.1", r.stdout); self.assertIn("0.6.0", r.stdout)

    def test_old_code_is_published_as_the_next_version(self):
        r = self.rollback(self.b, "0.6.0", "0.6.1 broke tags")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.hub_version(), "0.6.2")
        self.assertEqual(self.hub_file("app.py").stdout, "A = 1\nB = 1\n")
        self.assertNotEqual(self.hub_file("extra.py").returncode, 0)          # files added by the bad version are gone
        self.assertEqual(self.hub_file("tools/rollback.sh").returncode, 0)   # the tool itself stays
        self.assertIn("v0.6.2", sh(self.tmp, "git", "--git-dir", self.hub, "tag").stdout)
        log = sh(self.tmp, "git", "--git-dir", self.hub, "log", "-1", "--format=%s", "main").stdout
        self.assertIn("Roll back to 0.6.0 (published as 0.6.2): 0.6.1 broke tags", log)
        r = self.update(self.a)                                                # other PCs just update to it
        self.assertEqual((r.returncode, self.read(self.a, "app.py")), (0, "A = 1\nB = 1\n"))
        r = self.rollback(self.a, "0.6.1")                                     # and the rollback can be undone
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.hub_version(), self.hub_file("app.py").stdout), ("0.6.3", "A = 'bad'\nB = 1\n"))

    def test_refuses_unknown_version_and_unpushed_work(self):
        self.assertNotEqual(self.rollback(self.b, "9.9.9").returncode, 0)
        self.write(self.b, "app.py", "local edit\n")
        r = self.rollback(self.b, "0.6.0")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("update.sh first", r.stderr)
        self.assertEqual(self.hub_version(), "0.6.1")

    def test_failing_tests_publish_nothing(self):
        sh(self.b, "git", "pull", "-q")
        self.write(self.b, "tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n    def test(self): self.fail()\n")
        sh(self.b, "git", "commit", "-qam", "break tests"); sh(self.b, "git", "push", "-q", "origin", "main")
        sh(self.b, "git", "tag", "v0.6.2"); sh(self.b, "git", "push", "-q", "origin", "v0.6.2")
        sh(self.b, "git", "checkout", "-q", "v0.6.1", "--", "tests/test_ok.py")
        # roll back to v0.6.2 (whose tests fail) from the newest main
        sh(self.b, "git", "commit", "-qam", "fix tests"); sh(self.b, "git", "push", "-q", "origin", "main")
        before = sh(self.tmp, "git", "--git-dir", self.hub, "rev-parse", "main").stdout
        r = self.rollback(self.b, "0.6.2")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(sh(self.tmp, "git", "--git-dir", self.hub, "rev-parse", "main").stdout, before)


for _n in dir(Update):                                          # reuse the fixture, not update.sh's own tests
    if _n.startswith("test_") and _n not in Rollback.__dict__:
        setattr(Rollback, _n, None)
del Update                                                      # don't run update.sh's tests twice
