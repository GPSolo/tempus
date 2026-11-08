"""Run the workflow's reporting shell with a fake gh CLI; no GitHub/model calls."""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/upstream-sync.yml"
REPORT = textwrap.dedent(
    WORKFLOW.read_text().split("      - name: Publish review PR or report failure\n", 1)[1]
    .split("        run: |\n", 1)[1]
)


class SyncReportTest(unittest.TestCase):
    def report(self, merge="updated", verify="success", existing_pr="", issue=""):
        with tempfile.TemporaryDirectory(prefix="tempus-sync-report-") as directory:
            root = Path(directory)
            gh = root / "gh"
            gh.write_text(textwrap.dedent("""\
                #!/usr/bin/env bash
                set -eu
                echo "$*" >> "$GH_TEST_LOG"
                case "$*" in
                  'issue list '*) printf '%s' "$GH_TEST_ISSUE" ;;
                  'pr list '*) printf '%s' "$GH_TEST_PR" ;;
                  'pr view '*) printf 'false' ;;
                esac
                """))
            gh.chmod(0o755)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                       GH_TEST_LOG=str(root / "calls"), GH_TEST_PR=existing_pr,
                       GH_TEST_ISSUE=issue, GITHUB_STEP_SUMMARY=str(root / "summary"),
                       PREPARE_RESULT="success", MERGE_RESULT=merge, VERIFY_RESULT=verify,
                       REVISION="merged-sha", UPSTREAM_REVISION="upstream-sha",
                       RUN_URL="https://example.invalid/run/1")
            result = subprocess.run(["bash", "-c", REPORT], env=env, capture_output=True, text=True)
            calls = (root / "calls").read_text() if (root / "calls").exists() else ""
            return result, calls

    def test_noop_needs_no_issue_or_pr_api(self):
        result, calls = self.report(merge="noop", verify="skipped")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")

    def test_unchanged_schedule_does_not_report_again(self):
        result, calls = self.report(merge="unchanged", verify="skipped")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")

    def test_success_creates_review_pr(self):
        result, calls = self.report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pr create --base main --head automation/upstream-sync", calls)
        self.assertIn("Verified merged revision: merged-sha", calls)
        self.assertNotIn("issue create", calls)
        self.assertNotIn("pr merge", calls)

    def test_conflict_creates_issue_not_pr(self):
        result, calls = self.report(merge="conflict", verify="skipped")
        self.assertEqual(result.returncode, 1)
        self.assertIn("issue create --title Upstream sync needs attention", calls)
        self.assertNotIn("pr create", calls)

    def test_build_failure_updates_existing_issue_and_drafts_pr(self):
        result, calls = self.report(verify="failure", existing_pr="12", issue="34")
        self.assertEqual(result.returncode, 1)
        self.assertIn("pr ready 12 --undo", calls)
        self.assertIn("issue edit 34", calls)
        self.assertNotIn("issue create", calls)

    def test_success_updates_pr_and_closes_failure_issue(self):
        result, calls = self.report(existing_pr="12", issue="34")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pr edit 12", calls)
        self.assertIn("issue close 34", calls)
        self.assertNotIn("pr create", calls)


if __name__ == "__main__":
    unittest.main()
