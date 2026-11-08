# Fork integration (2026-11-07)

Upstream: https://github.com/eddyizm/tempus (`main`, `f8285641`).
Fork: https://github.com/GPSolo/tempus.

Before merging, inspected upstream `main` and `development` queue code and searched
open, closed and merged pull requests for queue, Play Next, swipe and FIFO changes.
No equivalent of this fork's settings-gated FIFO Play Next block or song-list
swipe-to-play-next was found. Related work:

- [#910](https://github.com/eddyizm/tempus/pull/910): Play Next under shuffle.
  Already present in the fork's original base; does not preserve repeated-insert order.
- [#1137](https://github.com/eddyizm/tempus/pull/1137): album-page Play Next/Add to Queue
  menu actions; integrated with the fork's explicit Play Next overload.
- [#1181](https://github.com/eddyizm/tempus/pull/1181): Compose queue sheet with
  swipe-to-remove. Ported the fork's right-swipe copy-insertion to this sheet rather
  than restoring the deleted RecyclerView queue fragment.

The merge retains upstream's namespace migration, service-owned QueueTarget,
release-safety checks, remote routing and new queue controls. New explicit artist
and playlist-row Play Next actions also opt into preservation; algorithmic Instant
Mix and Continuous Play retain the three-argument enqueue path.

Preservation remains local and memory-only, disabled by default. Upstream LAN
remote commands keep their existing protocol/ordering; this merge does not extend
the remote protocol to carry FIFO state.

## Manual verification still required

- Enable Preserve Play Next order; enqueue X then Y and verify X precedes Y.
- Repeat with shuffle enabled and with album/playlist batches.
- Swipe a queue row right: a copy is added and the original remains in place;
  repeat on the same row. Swipe left: upstream removal behavior remains.
- Verify song-list swipes after navigating away/back or refreshing adapters.
- Verify drag reorder/removal resets the block and Instant Mix remains unchanged.

## Automatic upstream sync

Owner-approved workflow: `.github/workflows/upstream-sync.yml`.

- Runs daily at **05:23 UTC**, or manually via **Actions → Sync upstream → Run workflow**
  on `main`. It is restricted to `GPSolo/tempus`.
- Merges upstream `main` and fork `main` into `automation/upstream-sync`, preserving
  history. It never force-pushes and never directly changes, approves or merges `main`.
- Builds and unit-tests **the exact merged revision**, once for each changed sync
  revision, covering both Tempus and Degoogled. It does not test every incoming
  upstream commit separately. Unchanged scheduled runs skip the expensive checks;
  manual dispatch retries verification of an existing pending sync revision.
- A successful check opens or updates one review PR. Merge/build failures create or
  update one **Upstream sync needs attention** issue. An existing PR becomes draft
  on failure; resolving conflicts requires a human. Retry manually after fixing it.
- Build jobs have a read-only token with persisted Git credentials disabled. PR/issue
  reporting runs separately, without checking out or executing the merged code.
- Uses `GITHUB_TOKEN`, not a personal access token. GitHub's **Allow GitHub Actions
  to create and approve pull requests** setting must be enabled; the workflow only
  creates PRs and never approves them. Token-created PRs do not trigger the separate
  PR workflow, so verification runs explicitly inside this workflow instead.
- Test reports are retained for seven days. No release signing secrets or server
  credentials are used. Manual on-device queue testing remains part of PR review.

**Cost requirement: no paid model inference is allowed.** The implementation is
stricter: it invokes **no AI models at all**, including free models, coding agents
or AI merge services. Conflicts are reported, not sent to a model. It uses standard
Linux GitHub-hosted runners, which are free for this public repository under GitHub's
current Actions policy; no larger/paid runners or external paid services are configured.
GitHub may disable scheduled workflows after 60 days of repository inactivity; check
the Actions page and re-enable the workflow if needed.
