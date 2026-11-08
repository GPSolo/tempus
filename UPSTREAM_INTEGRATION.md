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

No automatic upstream-sync workflow is included: its design requires owner review
before implementation.
