"""tools/update.sh against a throwaway "GitHub" (a bare repo) and two PCs (clones) — no network, no app install.

    python3 -m unittest tests.test_update
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATE = os.path.join(HERE, "..", "tools", "update.sh")


def sh(cwd, *args, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       env={"LABELDESK_ROLE": "publisher", **os.environ, "HOME": os.path.dirname(cwd), "GIT_CONFIG_NOSYSTEM": "1"})
    if check and r.returncode:
        raise AssertionError(f"{args} → {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


@unittest.skipUnless(shutil.which("git"), "needs git")
class Update(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hub = os.path.join(self.tmp, "hub.git")
        sh(self.tmp, "git", "init", "-q", "--bare", "-b", "main", self.hub)
        seed = self.pc("seed", clone=False)
        os.makedirs(os.path.join(seed, "tools")); os.makedirs(os.path.join(seed, "tests"))
        shutil.copy(UPDATE, os.path.join(seed, "tools", "update.sh"))
        self.write(seed, "VERSION", "0.6.0\n")
        self.write(seed, "app.py", "A = 1\nB = 1\n")
        self.write(seed, "tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n    def test(self): pass\n")
        sh(seed, "git", "add", "-A"); sh(seed, "git", "commit", "-qm", "seed"); sh(seed, "git", "push", "-q", "origin", "main")
        self.a, self.b = self.pc("pc-a"), self.pc("pc-b")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pc(self, name, clone=True):
        home = os.path.join(self.tmp, name); os.makedirs(home)
        d = os.path.join(home, "labeldesk")
        if clone:
            sh(home, "git", "clone", "-q", self.hub, d)
        else:
            os.makedirs(d); sh(d, "git", "init", "-q", "-b", "main"); sh(d, "git", "remote", "add", "origin", self.hub)
        sh(d, "git", "config", "user.name", name); sh(d, "git", "config", "user.email", f"{name}@example.invalid")
        return d

    def write(self, d, rel, text):
        with open(os.path.join(d, rel), "w") as f:
            f.write(text)

    def read(self, d, rel):
        with open(os.path.join(d, rel)) as f:
            return f.read()

    def update(self, d):
        return sh(d, "bash", "tools/update.sh", check=False)

    def hub_version(self):
        return sh(self.tmp, "git", "--git-dir", self.hub, "show", "main:VERSION").stdout.strip()

    def test_nothing_changed_is_a_no_op(self):
        r = self.update(self.a)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already up to date", r.stdout)
        self.assertEqual(self.hub_version(), "0.6.0")

    def test_local_edit_is_committed_bumped_tagged_and_pushed(self):
        self.write(self.a, "app.py", "A = 2\nB = 1\n")
        r = self.update(self.a)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.hub_version(), "0.6.1")
        self.assertIn("v0.6.1", sh(self.tmp, "git", "--git-dir", self.hub, "tag").stdout)
        r = self.update(self.b)                                             # the other PC just gets it
        self.assertEqual((r.returncode, self.read(self.b, "app.py"), self.read(self.b, "VERSION").strip()), (0, "A = 2\nB = 1\n", "0.6.1"))

    def test_both_pcs_changed_different_lines_merge_into_the_next_version(self):
        self.write(self.a, "app.py", "A = 2\nB = 1\n"); self.assertEqual(self.update(self.a).returncode, 0)
        self.write(self.b, "other.py", "C = 1\n")                         # b hasn't seen a's change yet
        r = self.update(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.read(self.b, "app.py"), self.hub_version()), ("A = 2\nB = 1\n", "0.6.2"))
        self.assertEqual(self.update(self.a).returncode, 0)                 # and a gets b's file
        self.assertEqual(self.read(self.a, "other.py"), "C = 1\n")

    def test_conflict_changes_nothing_and_keeps_local_work(self):
        self.write(self.a, "app.py", "A = 2\nB = 1\n"); self.assertEqual(self.update(self.a).returncode, 0)
        self.write(self.b, "app.py", "A = 3\nB = 1\n")
        r = self.update(self.b)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual((self.read(self.b, "app.py"), self.hub_version()), ("A = 3\nB = 1\n", "0.6.1"))
        self.assertEqual(sh(self.b, "git", "status", "--porcelain").stdout, "")              # clean, not mid-rebase
        self.assertIn("before update", sh(self.b, "git", "log", "-1", "--format=%s").stdout)  # work kept as a commit

    def test_failing_tests_block_the_push(self):
        self.write(self.a, "tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n    def test(self): self.fail()\n")
        r = self.update(self.a)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.hub_version(), "0.6.0")

    def test_new_data_files_are_never_committed(self):
        self.write(self.a, "real-ups-label.pdf", "%PDF customer address")
        self.write(self.a, "notes.md", "a new doc\n")
        r = self.update(self.a)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("real-ups-label.pdf", r.stdout)                                       # listed, not committed
        files = sh(self.tmp, "git", "--git-dir", self.hub, "ls-tree", "-r", "--name-only", "main").stdout.split()
        self.assertIn("notes.md", files)
        self.assertNotIn("real-ups-label.pdf", files)

    def test_a_version_set_by_the_change_is_kept(self):
        self.write(self.a, "VERSION", "0.7.0\n"); self.write(self.a, "app.py", "A = 9\nB = 1\n")
        self.assertEqual(self.update(self.a).returncode, 0)
        self.assertEqual(self.hub_version(), "0.7.0")

    def as_technician(self, d, *args):
        """update.sh on a technician's PC (no gh on PATH: the pull request link is printed instead)."""
        bin_ = os.path.join(self.tmp, "nogh"); os.makedirs(bin_, exist_ok=True)
        with open(os.path.join(bin_, "gh"), "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        r = subprocess.run(["bash", "tools/update.sh", *args], cwd=d, capture_output=True, text=True,
                           env={**os.environ, "LABELDESK_ROLE": "contributor", "PATH": bin_ + os.pathsep + os.environ["PATH"],
                                "HOME": os.path.dirname(d), "GIT_CONFIG_NOSYSTEM": "1"})
        return r

    def hub_branches(self):
        return sh(self.tmp, "git", "--git-dir", self.hub, "branch", "--format=%(refname:short)").stdout.split()

    def test_a_technicians_change_becomes_a_pull_request_not_a_version(self):
        self.write(self.b, "app.py", "A = 1\nB = 'tech'\n")
        r = self.as_technician(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("open the pull request", r.stdout)
        self.assertEqual((self.hub_version(), sh(self.tmp, "git", "--git-dir", self.hub, "show", "main:app.py").stdout),
                         ("0.6.0", "A = 1\nB = 1\n"))                       # main untouched
        [branch] = [x for x in self.hub_branches() if x.startswith("change/")]
        self.assertEqual(sh(self.tmp, "git", "--git-dir", self.hub, "show", f"{branch}:app.py").stdout, "A = 1\nB = 'tech'\n")
        self.assertEqual(sh(self.tmp, "git", "--git-dir", self.hub, "tag").stdout.strip(), "")        # no version, no tag
        self.write(self.b, "app.py", "A = 1\nB = 'tech2'\n")                  # more work: same branch, same PR
        self.assertEqual(self.as_technician(self.b).returncode, 0)
        self.assertEqual([x for x in self.hub_branches() if x.startswith("change/")], [branch])
        # the owner merges it on GitHub (here: a merge commit) and publishes; the technician's PC catches up
        sh(self.tmp, "git", "--git-dir", self.hub, "tag", "v0.6.0", "main")
        sh(self.a, "git", "fetch", "-q", "--tags", "origin", branch)
        sh(self.a, "git", "merge", "-q", "--no-ff", "-m", "Merge pull request #1", f"origin/{branch}")
        sh(self.a, "git", "push", "-q", "origin", "main")
        r = self.update(self.a)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("published LabelDesk 0.6.1", r.stdout)
        r = self.as_technician(self.b)
        self.assertEqual((r.returncode, self.read(self.b, "VERSION").strip()), (0, "0.6.1"), r.stdout + r.stderr)
        self.assertEqual(sh(self.b, "git", "config", "--get", "labeldesk.proposal", check=False).stdout, "")

    def test_owner_publishes_merged_pull_requests_once(self):
        sh(self.tmp, "git", "--git-dir", self.hub, "tag", "v0.6.0", "main")
        self.write(self.b, "app.py", "A = 1\nB = 9\n"); sh(self.b, "git", "commit", "-qam", "Fix B")
        sh(self.b, "git", "push", "-q", "origin", "HEAD:main")                 # as if a PR was merged on GitHub
        r = self.update(self.a)
        self.assertIn("published LabelDesk 0.6.1", r.stdout, r.stderr)
        self.assertIn("already up to date", self.update(self.a).stdout)       # nothing new: no 0.6.2

    def test_a_technician_cannot_roll_back(self):
        shutil.copy(os.path.join(HERE, "..", "tools", "rollback.sh"), os.path.join(self.b, "tools", "rollback.sh"))
        r = subprocess.run(["bash", "tools/rollback.sh", "0.6.0"], cwd=self.b, capture_output=True, text=True,
                           env={**os.environ, "LABELDESK_ROLE": "contributor", "HOME": self.tmp})
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertIn("gh issue create", r.stderr)

    def switch(self, d, *args, role="contributor"):
        for t in ("switch-version.sh", "rollback.sh"):
            shutil.copy(os.path.join(HERE, "..", "tools", t), os.path.join(d, "tools", t))
        return subprocess.run(["bash", "tools/switch-version.sh", *args], cwd=d, capture_output=True, text=True,
                              env={**os.environ, "LABELDESK_ROLE": role, "HOME": os.path.dirname(d), "GIT_CONFIG_NOSYSTEM": "1"})

    def held(self, d):
        import json
        sub = "Library/Application Support/LabelDesk" if sys.platform == "darwin" else ".config/labeldesk"
        try:
            return json.load(open(os.path.join(os.path.dirname(d), sub, "config.json"))).get("hold_version")
        except OSError:
            return None

    def test_switch_this_pc_to_an_older_version_and_back(self):
        sh(self.tmp, "git", "--git-dir", self.hub, "tag", "v0.6.0", "main")
        self.write(self.a, "app.py", "A = 'new'\nB = 1\n")
        self.assertEqual(self.update(self.a).returncode, 0)                    # owner publishes 0.6.1
        sh(self.b, "git", "pull", "-q")
        r = self.switch(self.b, "0.6.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.read(self.b, "app.py"), self.read(self.b, "VERSION").strip(), self.held(self.b)),
                         ("A = 1\nB = 1\n", "0.6.0", "0.6.0"))
        self.assertEqual(self.hub_version(), "0.6.1")                          # GitHub untouched
        r = self.switch(self.b, "newest")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.read(self.b, "app.py"), self.held(self.b)), ("A = 'new'\nB = 1\n", None))

    def test_switch_refuses_to_lose_local_work_and_every_pc_is_owner_only(self):
        sh(self.tmp, "git", "--git-dir", self.hub, "tag", "v0.6.0", "main")
        self.write(self.b, "app.py", "local edit\n")
        r = self.switch(self.b, "0.6.0")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("update.sh first", r.stderr)
        sh(self.b, "git", "checkout", "-q", "--", "app.py")
        r = self.switch(self.b, "0.6.0", "--everyone")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)                 # rollback.sh: only the owner publishes

    def changelog_pc(self):
        """PC a with a CHANGELOG.md like the real one, pushed (as if it had always been there)."""
        self.write(self.a, "CHANGELOG.md", "# What's new\n\n## Unreleased\n\n## 0.6.0 — 2026-10-01\n- old\n")
        sh(self.a, "git", "add", "CHANGELOG.md"); sh(self.a, "git", "commit", "-qm", "changelog"); sh(self.a, "git", "push", "-q")
        return self.a

    def hub_changelog(self):
        return sh(self.tmp, "git", "--git-dir", self.hub, "show", "main:CHANGELOG.md").stdout

    def test_unreleased_notes_become_the_version(self):
        a = self.changelog_pc()
        self.write(a, "app.py", "A = 3\nB = 1\n")
        self.write(a, "CHANGELOG.md", self.read(a, "CHANGELOG.md").replace("## Unreleased\n", "## Unreleased\n- Bigger font\n"))
        self.assertEqual(self.update(a).returncode, 0)
        log = self.hub_changelog()
        self.assertRegex(log, r"## Unreleased\n\n## 0\.6\.1 — \d{4}-\d\d-\d\d\n- Bigger font\n\n## 0\.6\.0")

    def test_no_notes_uses_the_commit_messages(self):
        a = self.changelog_pc()
        self.write(a, "app.py", "A = 4\nB = 1\n")
        sh(a, "git", "commit", "-qam", "Tag font bigger")
        self.assertEqual(self.update(a).returncode, 0)
        log = self.hub_changelog()
        self.assertIn("\n- Tag font bigger\n", log.split("## 0.6.1", 1)[1].split("## 0.6.0")[0])
        self.assertNotIn("changelog", log.split("## 0.6.1", 1)[1].split("## 0.6.0")[0])


if __name__ == "__main__":
    unittest.main()
