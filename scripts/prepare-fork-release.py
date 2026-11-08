"""Select the latest stable upstream release, without inference or paid services."""

import json
import os
from pathlib import Path
import re
import subprocess


QUEUE_COMMIT = "d45fafbe"


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def version(config):
    name = re.search(r"\bversionName\s+['\"]([^'\"]+)['\"]", config)
    code = re.search(r"\bversionCode\s+(\d+)", config)
    if not name or not code:
        raise ValueError("Cannot read the app version; manual review is required")
    return name.group(1), int(code.group(1))


def select_release(upstream, existing, local_version, upstream_version):
    tag = upstream["tag_name"]
    if upstream.get("draft") or upstream.get("prerelease") or not re.fullmatch(r"v\d+(?:\.\d+){1,3}", tag):
        raise ValueError("Only stable numeric upstream release tags are supported")
    fork_tag = f"{tag}-queue"
    if any(release["tag_name"] == fork_tag for page in existing for release in page):
        return fork_tag, "exists"
    if local_version != upstream_version:
        return fork_tag, "version-mismatch"
    return fork_tag, "ready"


def check_existing_tag(tag, revision):
    refs = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    if refs:
        targets = dict(line.split()[::-1] for line in refs.splitlines())
        target = targets.get(f"refs/tags/{tag}^{{}}", targets.get(f"refs/tags/{tag}"))
        if target != revision:
            raise ValueError("Existing fork tag points elsewhere; refusing to move it or publish mismatched APKs")


def main():
    upstream = json.loads(Path("upstream-release.json").read_text())
    existing = json.loads(Path("fork-releases.json").read_text())
    # Validate the tag before using it as a Git ref.
    tag, state = select_release(upstream, existing, (None, None), (None, None))
    outputs = {"publish": "false", "tag": tag}
    if state != "exists":
        git("fetch", "--no-tags", "https://github.com/eddyizm/tempus.git", f"refs/tags/{upstream['tag_name']}")
        upstream_sha = git("rev-parse", "FETCH_HEAD^{commit}")
        revision = git("rev-parse", "HEAD")
        integrated = subprocess.run(["git", "merge-base", "--is-ancestor", upstream_sha, revision]).returncode == 0
        if not integrated:
            state = "awaiting-reviewed-sync"
        else:
            git("merge-base", "--is-ancestor", QUEUE_COMMIT, revision)
            git("cat-file", "-e", f"{revision}:app/src/test/java/com/eddyizm/tempus/service/MediaManagerPlayNextOrderTest.java")
            tag, state = select_release(
                upstream, existing, version(git("show", f"{revision}:app/build.gradle")),
                version(git("show", f"{upstream_sha}:app/build.gradle"))
            )
            if state == "ready":
                check_existing_tag(tag, revision)
                outputs.update(publish="true", revision=revision, upstream_sha=upstream_sha,
                               upstream_tag=upstream["tag_name"])
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in outputs.items():
            output.write(f"{key}={value}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        summary.write(f"Fork release `{tag}`: **{state}**. No existing tags or releases were changed.\n")


if __name__ == "__main__":
    main()
