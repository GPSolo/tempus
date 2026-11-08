"""Test release selection and immutable tag guards without GitHub/model calls."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "fork_release", Path(__file__).resolve().parents[1] / "prepare-fork-release.py"
)
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)


class ForkReleaseTest(unittest.TestCase):
    def setUp(self):
        self.upstream = {"tag_name": "v4.31.0", "draft": False, "prerelease": False}
        self.version = ("4.31.0", 52)

    def test_matching_stable_gets_queue_suffix(self):
        self.assertEqual(
            RELEASE.select_release(self.upstream, [[]], self.version, self.version),
            ("v4.31.0-queue", "ready"),
        )

    def test_does_not_republish_existing_releases_or_drafts(self):
        for draft in (True, False):
            with self.subTest(draft=draft):
                existing = [[{"tag_name": "v4.31.0-queue", "draft": draft}]]
                self.assertEqual(RELEASE.select_release(
                    self.upstream, existing, self.version, self.version
                )[1], "exists")

    def test_later_main_version_is_not_mislabeled(self):
        self.assertEqual(RELEASE.select_release(
            self.upstream, [[]], ("4.32.0", 53), self.version
        )[1], "version-mismatch")

    def test_changed_version_code_is_not_mislabeled(self):
        self.assertEqual(RELEASE.select_release(
            self.upstream, [[]], ("4.31.0", 53), self.version
        )[1], "version-mismatch")

    def test_rejects_prereleases_drafts_and_unsafe_tags(self):
        for change in ({"prerelease": True}, {"draft": True},
                       {"tag_name": "v4.31.2-dev"}, {"tag_name": "--upload-pack=bad"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                RELEASE.select_release(self.upstream | change, [[]], self.version, self.version)

    def test_reads_actual_upstream_version_metadata(self):
        self.assertEqual(RELEASE.version("versionCode 52\nversionName '4.31.0'"), self.version)
        with self.assertRaises(ValueError):
            RELEASE.version("missing version metadata")

    def test_missing_tag_can_be_created(self):
        with patch.object(RELEASE, "git", return_value=""):
            RELEASE.check_existing_tag("v4.31.0-queue", "fork-sha")

    def test_matching_annotated_tag_is_allowed(self):
        refs = "tag-object refs/tags/v4.31.0-queue\nfork-sha refs/tags/v4.31.0-queue^{}"
        with patch.object(RELEASE, "git", return_value=refs):
            RELEASE.check_existing_tag("v4.31.0-queue", "fork-sha")

    def test_mismatched_tag_is_never_moved(self):
        with patch.object(RELEASE, "git", return_value="other-sha refs/tags/v4.31.0-queue"):
            with self.assertRaises(ValueError):
                RELEASE.check_existing_tag("v4.31.0-queue", "fork-sha")


if __name__ == "__main__":
    unittest.main()
