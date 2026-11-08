"""Exercise the real merge script against local Git repositories, without APIs/models."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "prepare-upstream-sync.sh"
SYNC_BRANCH = "automation/upstream-sync"


class UpstreamSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tempus-sync-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream"
        self.origin = self.root / "origin.git"
        self.git(self.root, "init", "--initial-branch=main", str(self.upstream))
        self.git(self.upstream, "config", "user.name", "Test")
        self.git(self.upstream, "config", "user.email", "test@example.invalid")
        self.commit(self.upstream, "shared.txt", "base\n")
        self.git(self.root, "clone", "--bare", str(self.upstream), str(self.origin))
        self.fork = self.clone("fork")
        self.commit(self.fork, "fork-feature.txt", "preserve FIFO\n")
        self.git(self.fork, "push", "origin", "main")

    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
        ).stdout.strip()

    def clone(self, name):
        path = self.root / name
        self.git(self.root, "clone", str(self.origin), str(path))
        self.git(path, "config", "user.name", "Test")
        self.git(path, "config", "user.email", "test@example.invalid")
        return path

    def commit(self, repo, name, content):
        (repo / name).write_text(content)
        self.git(repo, "add", name)
        self.git(repo, "commit", "-m", f"Update {name}")
        return self.git(repo, "rev-parse", "HEAD")

    def sync(self, name="runner", force=False):
        repo = self.clone(name)
        output = self.root / f"{name}-outputs"
        env = dict(os.environ, GITHUB_OUTPUT=str(output), UPSTREAM_URL=str(self.upstream),
                   FORCE_VERIFY=str(force).lower())
        subprocess.run(["bash", str(SCRIPT)], cwd=repo, env=env,
                       text=True, capture_output=True, check=True)
        return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def remote_revision(self, branch):
        return self.git(self.origin, "rev-parse", f"refs/heads/{branch}")

    def test_up_to_date_does_not_create_sync_branch(self):
        self.assertEqual(self.sync(), {"result": "noop", "verify": "false"})
        self.assertEqual(self.git(self.origin, "branch", "--list", SYNC_BRANCH), "")

    def test_merge_preserves_both_histories_and_main(self):
        main = self.remote_revision("main")
        upstream = self.commit(self.upstream, "upstream.txt", "upstream update\n")
        result = self.sync()
        self.assertEqual(result["result"], "updated")
        self.assertEqual(result["verify"], "true")
        self.assertEqual(result["upstream_revision"], upstream)
        self.assertEqual(self.remote_revision("main"), main)
        self.git(self.origin, "merge-base", "--is-ancestor", main, SYNC_BRANCH)
        self.git(self.origin, "merge-base", "--is-ancestor", upstream, SYNC_BRANCH)
        self.assertEqual(self.git(self.origin, "show", f"{SYNC_BRANCH}:fork-feature.txt"), "preserve FIFO")

    def test_unchanged_schedule_skips_but_manual_retries(self):
        self.commit(self.upstream, "upstream.txt", "update\n")
        initial = self.sync()
        unchanged = self.sync("second")
        self.assertEqual(unchanged["result"], "unchanged")
        self.assertEqual(unchanged["verify"], "false")
        retry = self.sync("third", force=True)
        self.assertEqual(retry["result"], "unchanged")
        self.assertEqual(retry["verify"], "true")
        self.assertEqual(retry["revision"], initial["revision"])

    def test_updated_fork_is_merged_and_reverified(self):
        self.commit(self.upstream, "upstream.txt", "update\n")
        initial = self.sync()
        main = self.commit(self.fork, "fork-feature.txt", "improved FIFO\n")
        self.git(self.fork, "push", "origin", "main")
        result = self.sync("second")
        self.assertEqual(result["result"], "updated")
        self.assertEqual(result["verify"], "true")
        self.git(self.origin, "merge-base", "--is-ancestor", initial["revision"], SYNC_BRANCH)
        self.git(self.origin, "merge-base", "--is-ancestor", main, SYNC_BRANCH)

    def test_conflict_does_not_push_or_modify_main(self):
        main = self.commit(self.fork, "shared.txt", "fork version\n")
        self.git(self.fork, "push", "origin", "main")
        self.commit(self.upstream, "shared.txt", "upstream version\n")
        result = self.sync()
        self.assertEqual(result, {"result": "conflict", "verify": "false"})
        self.assertEqual(self.remote_revision("main"), main)
        self.assertEqual(self.git(self.origin, "branch", "--list", SYNC_BRANCH), "")

    def test_new_upstream_update_keeps_existing_sync_history(self):
        self.commit(self.upstream, "upstream.txt", "first\n")
        initial = self.sync()
        self.commit(self.upstream, "upstream.txt", "second\n")
        result = self.sync("second")
        self.assertEqual(result["result"], "updated")
        self.git(self.origin, "merge-base", "--is-ancestor", initial["revision"], SYNC_BRANCH)
        self.assertEqual(self.git(self.origin, "show", f"{SYNC_BRANCH}:upstream.txt"), "second")


if __name__ == "__main__":
    unittest.main()
