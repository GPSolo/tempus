#!/usr/bin/env bash
# Runs in a disposable Actions checkout. No AI/model inference is permitted.
set -euo pipefail

: "${GITHUB_OUTPUT:?Run in an Actions checkout or an isolated test repository}"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/eddyizm/tempus.git}"
SYNC_BRANCH="automation/upstream-sync"

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git fetch --no-tags origin main
git fetch --no-tags "$UPSTREAM_URL" main
upstream_revision="$(git rev-parse FETCH_HEAD)"

if git merge-base --is-ancestor "$upstream_revision" origin/main; then
    echo 'result=noop' >> "$GITHUB_OUTPUT"
    echo 'verify=false' >> "$GITHUB_OUTPUT"
    exit 0
fi

previous_revision=''
if git ls-remote --exit-code --heads origin "$SYNC_BRANCH"; then
    git fetch --no-tags origin "refs/heads/$SYNC_BRANCH:refs/remotes/origin/$SYNC_BRANCH"
    previous_revision="$(git rev-parse "origin/$SYNC_BRANCH")"
    git switch --create "$SYNC_BRANCH" "origin/$SYNC_BRANCH"
else
    git switch --create "$SYNC_BRANCH" origin/main
fi

# Preserve both the fork and previous sync commits. Never reset or force-push.
for revision in origin/main "$upstream_revision"; do
    if ! git merge --no-edit "$revision"; then
        echo 'Merge failed; manual resolution is required.' >&2
        git diff --name-only --diff-filter=U
        echo 'result=conflict' >> "$GITHUB_OUTPUT"
        echo 'verify=false' >> "$GITHUB_OUTPUT"
        exit 0
    fi
done

revision="$(git rev-parse HEAD)"
echo "revision=$revision" >> "$GITHUB_OUTPUT"
echo "upstream_revision=$upstream_revision" >> "$GITHUB_OUTPUT"
if [[ "$revision" != "$previous_revision" ]]; then
    git push origin "HEAD:refs/heads/$SYNC_BRANCH"
    echo 'result=updated' >> "$GITHUB_OUTPUT"
    echo 'verify=true' >> "$GITHUB_OUTPUT"
else
    echo 'result=unchanged' >> "$GITHUB_OUTPUT"
    # Manual dispatch can retry a failed build without creating another commit.
    echo "verify=${FORCE_VERIFY:-false}" >> "$GITHUB_OUTPUT"
fi
