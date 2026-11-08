# Fork integration notes

The local changes below were committed and merged with upstream `main` in November 2026.
Upstream migrated the namespace to `com.eddyizm.tempus` and replaced `PlayerQueueFragment`
with `ui/queue/PlayerQueue{Bridge,Sheet,List,Item}.kt`. The fork's right-swipe action now
lives in that Compose queue; left-swipe still removes and right-swipe inserts a copy.
The historical paths and pre-existing build limitations below describe the original work;
upstream now has a lint baseline and additional unit tests. Keep using the writable SDK
and flavor-specific assemble/test tasks. The Songs browser remains a plan, not implemented.

The debug-login hook now uses `tasks.configureEach` (AGP removed `applicationVariants`)
and supports the upstream `play` flavor as well. FIFO preservation is local; LAN remote
queue commands retain upstream ordering and protocol. See `UPSTREAM_INTEGRATION.md`.

Automatic upstream syncing is owner-approved and implemented in
`.github/workflows/upstream-sync.yml`: daily/manual review PRs, merged-revision
builds/tests for both flavors, no force-pushes or automatic merges. **No paid model
inference is permitted; the implementation invokes no AI models at all.** Never add
model-based conflict resolution without fresh owner approval. See
`UPSTREAM_INTEGRATION.md` for operation and retry instructions.

Owner-approved fork releases follow stable upstream versions with `-queue` tags,
preserving existing tags. `.github/workflows/fork-release.yml` builds reviewed fork
`main` including queue changes, checks upstream ancestry/version metadata, tests both
flavors, and signs using dedicated fork secrets in an isolated job. No model calls.
See `FORK_RELEASES.md`; never rotate or overwrite the fork signing key casually.

# AGENTS.md — Tempo codebase orientation (for AI agents)

This file is a handoff for any model (or human) working on this repo. It documents **uncommitted
work in progress** on top of the stock Tempo app (a Subsonic client for Android, package
`com.cappielloantonio.tempo`). Read it fully before touching queue/playback code. A human-readable
change log with the full `git diff` is in `LocalChanges.md`.

---

## 0. First: how to build and install (non-negotiable)

- **SDK location:** the system SDK at `/opt/android-sdk` is **not writable**. Always set
  `ANDROID_HOME=/home/gp/Android/Sdk` for every Gradle invocation. Platform 36 + build-tools are
  already installed there.
- **Never run `./gradlew build`** — it is broken project-wide by ~519 pre-existing lint errors
  (no lint baseline; plus `MediaRouteActionProvider` in the shared `main_page_menu.xml` vs.
  `media3.cast` being tempus-only). **Use `assemble*` tasks only.**
- Flavors: `tempus` (`com.eddyizm.tempus`), `degoogled` (`com.eddyizm.degoogled.tempus`); debug
  builds append `.debug` to the package.
- Working commands:
  - `ANDROID_HOME=/home/gp/Android/Sdk ./gradlew :app:assembleDegoogledDebug :app:assembleTempusDebug`
  - `ANDROID_HOME=/home/gp/Android/Sdk ./gradlew :app:installDegoogledDebug` — installs **and**
    auto-seeds the saved login (see §5).
- Only new lint errors this work introduced: the 2 `MissingTranslation` warnings for the new strings.
- No automated tests exist in this area; verification is manual on-device. Devices seen:
  physical `3A210DLJH000F1` and an emulator `Pixel 8 - 17`. `adb` requires exactly one target.
- The repo root also contains untracked Eclipse artifacts (`.project`, `.settings/`, `app/.classpath`,
  `app/.project`) that are **not ours** — ignore them, never commit them.

---

## 1. Architecture you must understand before editing

Queue/playback pipeline (top to bottom):

1. **UI layer** (fragments/adapters) — shows lists, handles taps/swipes.
2. **`com.cappielloantonio.tempo.service.MediaManager`** (Java) — the hub. Static methods take a
   `ListenableFuture<MediaBrowser>`, add a listener, and mutate the media session timeline **and**
   the Room queue DB (via `getQueueRepository()`, which drives the bottom-sheet queue list through
   `queueRepository.getLiveQueue()`).
3. **Custom commands** — `MediaManager` sends a `SessionCommand` with a `Bundle` of args →
   `BaseSessionCallback` reads them → calls into the service.
4. **`com.cappielloantonio.tempo.service.BaseMediaService`** (Kotlin) — owns the `player`; the
   shuffle-order fixup lives here.
5. **Room** (`QueueRepository`) — the source of truth for the queue *list* UI.

Login: `MainActivity.init()` skips the login screen if `Preferences.getPassword() != null`;
`App.java` builds the Subsonic client from prefs keys `server`, `user`, `password`, `token`,
`salt`, `low_security`, `client_cert`.

---

## 2. Feature A — "Preserve Play Next order" (settings-gated FIFO block)

### What it does
When the switch **Preserve "Play Next" order** is enabled, explicit Play Next actions accumulate
into a **contiguous block** right after the current track, Spotify-style: Play Next X then Y
produces `A B X Y C D` instead of `A B Y X C D`. Default is **off**, preserving stock LIFO behavior.

### How it works — the in-memory block (READ THIS)
`MediaManager` keeps two `static` fields:

```
playNextAnchorIndex  // media-session index of the current item when the block was started
playNextBlockLength  // number of Play Next items currently in the block
```

- `computePlayNextInsertPos(browser, count, preserveOrder)`:
  - `current == C.INDEX_UNSET` → reset, return 0.
  - `preserveOrder == false` → reset, return `current + 1` (stock behavior).
  - Anchor changed (`playNextAnchorIndex != current`) → re-anchor, reset block length.
  - Insert at `current + blockLength + 1`, grow `playNextBlockLength += count`.
- `resetPlayNextBlock()` is called on **every manual queue edit**: `shuffle`, `swap` (drag
  reorder), `remove`, `removeRange`, `deleteRange`. This is deliberate: a user dragging rows means
  the block's positions are invalid, so the block starts over.

### The two `enqueue` overloads (semantic split — do not conflate)
- **3-arg** `enqueue(future, items, playImmediatelyAfter)` → delegates with `preservePlayNextOrder=false`.
  Used by Continuous Play / Instant Mix / queue-append paths. They keep the stock `current + 1`
  or end-of-queue insertion and **never** touch the block.
- **4-arg** `enqueue(future, items, playImmediatelyAfter, preservePlayNextOrder)` → when the flag is
  `true` **and** the setting is on, it goes through the block logic. The 4 **explicit** Play Next
  call sites (Song/Album/Playlist/Downloaded bottom sheets) pass `(…, true, true)`.

### Shuffle coordination
Under shuffle the timeline insert lands where the UI says, but shuffle order decides the *actual*
play order. The stock code had a one-shot async fixup (`requestPlayNextFixup`) triggered from
`onTimelineChanged` when the target item count becomes visible — because `addMediaItems`' own
internal shuffle insert would otherwise clobber it. That mechanism is extended:
- `PlayNextRequest` gained `preserveOrder` + `blockLengthBefore`.
- `BaseMediaService.tryApplyPlayNextFixup` splices the new items **after the last block item**
  in shuffle order (not after `current+1`) when preserving order.
- Constants: `PLAY_NEXT_PRESERVE_ORDER`, `PLAY_NEXT_BLOCK_LENGTH` carried through
  `MediaManager → BaseSessionCallback → BaseMediaService`.

### Invariants — do not break
- The block is **ephemeral** (process memory only). It is intentionally **not persisted** and there
  is **no Room migration**. Do not "improve" this to persist without being asked.
- Only **explicit** Play Next actions build the block. Algorithmic paths (Continuous Play, Instant
  Mix, end-of-queue append) must stay at `current + 1` / end.
- The block re-anchors when the current item changes and resets on manual edits.

---

## 3. Feature B — Swipe to play next + swipe indicators

### `PlayNextSwipeHelper` (new file, `util/PlayNextSwipeHelper.java`)
Right-swipe a song row → `MediaManager.enqueue(browser, song, true, true)` + toast "Added to Play
Next". Design decisions that matter:

- **Lazy inputs.** It takes `Supplier<ListenableFuture<MediaBrowser>>` and
  `Function<Integer, Child> itemAt` instead of resolved values, because fragments only build the
  `MediaBrowser` in `onStart` and adapters repopulate asynchronously.
- **One helper per recycler — replace, don't stack.** Fragments recreate adapters (and re-run
  `attach()`) on every LiveData emission. Without dedup this stacks `ItemTouchHelper`s, and the
  stale helper's view holder references a freshly-recreated adapter whose `ListAdapter` differ is
  still empty → `getBindingAdapterPosition()` returns e.g. `5` but `getItem(5)` throws on
  `Collections.emptyList()`. Fix: `attach()` keeps a `WeakHashMap<RecyclerView, ItemTouchHelper>`,
  detaches the previous helper (`attachToRecyclerView(null)`) before attaching a new one.
- **Bounds-guard every access in `onSwiped`.** Resolve the item only when
  `position != NO_POSITION && 0 <= position < adapter.getItemCount()`, and only then
  `notifyItemChanged`. If the position is stale, the swipe is a silent no-op (never a crash).
  Same defensive rule applies to `SongHorizontalAdapter.getItem` (returns `null` on OOB) and any
  new adapter you wire up.
- **`drawSwipeAction(canvas, viewHolder, dX, bgColor, icon)`** paints the affordance behind the row:
  filled background over the *revealed* area + a 24dp icon vertically centered at the row's edge
  (`dX > 0` → icon near the left edge; `dX < 0` → near the right edge). Used by both this helper
  and the queue screen. Colors: `swipeQueueBackground` (green), `swipeRemoveBackground` (red),
  icons `ic_queue_white` / `ic_close_white`.

### Attach sites
`AlbumPageFragment` (top songs), `ArtistPageFragment` (top songs), `HomeTabMusicFragment` (top
songs + starred), `PlaylistPageFragment`, `SongListPageFragment`, `SearchFragment`,
`DirectoryFragment`. `MusicDirectoryAdapter` got a `getItem(int)`.

### Queue screen (`PlayerQueueFragment`) — the swipe semantics that were deliberately changed
- Swipes enabled: `UP | DOWN` (drag reorder) + `LEFT | RIGHT`.
- **LEFT = remove** the row (pre-existing).
- **RIGHT = play next inserts a NEW COPY** of the swiped track via
  `MediaManager.enqueue(future, items.get(position), true, true)` — it must **not move** the
  existing row. The queue grows by one and every other row stays put. The list refreshes on its
  own through Room (`getLiveQueue()`), because `enqueue` writes the queue DB.
- The old move-based `MediaManager.playNext(ListenableFuture, List<Child>, int)` was **removed**
  after this change (it was only used by the queue swipe). Do not reintroduce it for the swipe;
  if a move behavior is ever wanted it must be a separate affordance.
- Bounds-check `position` against `playerSongQueueAdapter.getItems().size()` before touching the
  list (same stale-position hazard as §3).

---

## 4. Known limitations (accepted, documented in code)
- Manual queue edits (drag reorder, remove, swipe) do **not** run the shuffle-order fixup — the
  same limitation the stock drag/remove had. Only the explicit Play Next insert path does.
- The Play Next block is memory-only, so it resets when the app process dies or the queue is edited.

---

## 5. Debug auto-login seeding (dev workflow)

- `app/build.gradle` — `android.applicationVariants.all { … installTask.doLast { … } }` runs
  `scripts/seed-debug-login.sh <flavor>` after every `install*Debug`. Note: uses `ProcessBuilder`
  (not `project.exec`, which Gradle 9.4/AGP 9 could not resolve inside that `doLast` scope).
- `scripts/seed-debug-login.sh` — reads `debug-server.properties` from the repo root
  (gitignored; template in `debug-server.properties.example`), pushes an XML prefs file to
  `/data/local/tmp`, then `adb shell "run-as <pkg> sh -c 'mkdir -p shared_prefs && cp … && chmod 600 …'"`
  to write `<pkg>_preferences.xml` with `server`/`server_id`/`user`/`password`/`low_security`.
  It silently no-ops when no device or no props file is present, and exits non-zero on a malformed
  file. The app then skips the login screen (`MainActivity.init()` checks `Preferences.getPassword()`).
- Remember `adb install -r` already preserves app data across reinstalls; the seeding only matters
  for truly fresh installs (wiped data / new device).

---

## 6. Conventions & gotchas summary for agents
- Java files use the project's existing style (no external formatting tool configured; match
  neighbours). Kotlin files likewise.
- Do not add comments that restate the obvious; the existing codebase uses sparse explanatory
  comments, and the new block/fixup code carries a few high-value ones — preserve them.
- When adding a new swipe screen: call `PlayNextSwipeHelper.attach(rv, () -> browserFuture,
  adapter::getItem)` **after** `setAdapter`, ensure the adapter exposes `getItem(int)` (bounds-safe),
  and do not add a second `ItemTouchHelper` to the same recycler.
- When touching `MediaManager.enqueue`, keep the 3-arg/4-arg semantic split intact.
- Verify with the `assemble*` + `install*Debug` commands in §0. `./gradlew build` will fail on
  pre-existing lint noise — ignore those errors; only new errors introduced by your change matter.

---

## 7. Feature C — "Songs" library browser with client-side column sorting (WIP plan)

Status: **planned, not implemented.** Revisit this section before touching anything related; it is
the agreed design from the planning conversation. The user wants this implemented when they return.

### What it is
A new **Songs** screen reachable from the **Library tab** that shows the *entire* library as one
list, with a sort control (top-right action button with a **tabular/table icon**) that opens a
`PopupMenu` of columns. Rows stay **visually identical to today's `item_horizontal_track.xml`**
(cover + title + artist/album + duration) — no column values are shown on rows; the sort menu is the
only indication of the current ordering. Default sort on first open: **Date Added, newest first**.

### Verified API facts (do not re-litigate without new evidence)
- Navidrome has **no `getSongs`** Subsonic endpoint, and **ignores any `sortBy`/`sortOrder`/`sort`
  params** on `search3`/`getAlbumList`. Server-side sorting is not available → **sorting must be
  client-side** over the cached full list.
- `search3` **with an empty `query=""` returns the whole library**, paginated by `songCount` /
  `songOffset`. OpenSubsonic mandates empty-query support for offline sync; Navidrome PR #4382
  optimizes exactly this path. This is the pagination vehicle.
- Tempo's `SearchingClient.search3` already exists
  (`search3(query, songCount, songOffset, albumCount, albumOffset, artistCount, artistOffset)`).
  For the full-library call pass `query=""`, `songCount=500`, `albumCount=0`, `artistCount=0`.
- The song payload carries everything needed for the agreed columns: `created` (Date Added),
  `playCount` (Plays), `year`, `album`, `artist` (all already parsed in `Child.kt`), and
  `played` (Last Played) which Navidrome returns as an OpenSubsonic extension (`OpenSubsonicChild.played`,
  confirmed in real search3 JSON) but **Tempo's `Child.kt` does NOT parse today**.

### Per-context column availability (verified against Navidrome source)
- New Songs screen mirrors Navidrome's **Songs view** (`ui/src/song/SongList.jsx`): all of
  **Date Added, Last Played, Artist, Album, Year, Plays** are available.
- Navidrome's **playlist view** (`ui/src/playlist/PlaylistSongs.jsx`) has **NO `createdAt`
  (Date Added)** column — verified in current `master`. Album/Artist/Year/Plays/Last Played are
  present there. So a future playlist-screen sort menu must **omit Date Added**. Encode this as a
  per-context column whitelist in the sort utility, not as a hardcoded assumption in the UI.

### Implementation steps (agreed design)
1. **`Child.kt`** — add `played: Date?` (`@SerializedName("played")`) + entries in `equals`/`hashCode`.
2. **Room v21→22** — `@AutoMigration(from=21, to=22)` (additive, safe):
   - `CachedSong` table: `id` PK, `title`, `artist`, `album`, `year`, `playCount`, `created`,
     `played`, `duration`, `coverArtId`, `artistId`, `albumId`, `genre`, `track`, `discNumber`,
     `bitrate`, `starred`.
   - `SongCacheInfo` single-row table: `lastFetchedAt`, `lastServerScanAt`.
3. **`SongRepository.getSongs()`** — `LiveData<List<Child>>` from Room; if cache empty or stale,
   loop `search3("", 500, offset=i, 0, 0, 0, 0)` until a short page (< 500), persisting each page as
   it arrives so the first page renders instantly. Never block on the whole library before showing
   data.
4. **Auto-refresh** — on screen open call `ScanRepository.getScanStatus()`; if server
   `lastScan > stored lastServerScanAt` → re-paginate. If `scanning == true`, poll until it
   finishes, then refresh. **Pull-to-refresh** re-paginates unconditionally. Cost must stay at one
   tiny call per open when nothing changed.
5. **`ScanStatus.kt`** — currently only `isScanning`/`count`; add `lastScan: Date?` (plus
   `folderCount`, `scanType`, `error`, `elapsedTime`) for the auto-refresh trigger.
6. **`util/SongSort.java`** — enum of columns (Date Added, Last Played, Artist, Album, Year, Plays,
   + Title and Duration as extras) with null-safe comparators. Date/Plays default DESC, text/Year
   default ASC, never-played sorts last. Default selection: Date Added DESC.
7. **`SongsViewModel`** — applies the comparator and re-submits a sorted copy; no adapter changes.
   **Reuse `SongHorizontalAdapter` and `item_horizontal_track.xml` unchanged.**
8. **`SongsFragment`** + `songsFragment` nav destination + `action_libraryFragment_to_songsFragment`;
   Library sector (title + "See all" button) mirroring existing sectors in `fragment_library.xml` /
   `LibraryFragment`. Wire `PlayNextSwipeHelper.attach(...)` for swipe-to-play-next (Feature B).

### Invariants / gotchas
- Sort state is **only** the menu (active column checked, re-tap toggles asc/desc). Rows must not
  gain visible column values.
- Do **not** add a second `ItemTouchHelper` to the Songs recycler; attach the swipe helper after
  `setAdapter` (see §6).
- Keep the 3-arg/4-arg `MediaManager.enqueue` split untouched; the Songs screen plays/queues via
  the normal paths.
- Verify with `ANDROID_HOME=/home/gp/Android/Sdk ./gradlew :app:assembleTempusDebug :app:assembleDegoogledDebug`.
---

## Upstream agent guidance
# AGENTS.md - Tempus (Android Subsonic Client)

## Project Overview
**Tempus** is an open-source Android music client for Subsonic servers. Two product flavors:
- **tempus** (`com.eddyizm.tempus`) - GitHub release with Android Auto & Chromecast
- **degoogled** (`com.eddyizm.degoogled.tempus`) - IzzyOnDroid/F-Droid release, no Google services

## Build & Development

### Toolchain
- **Gradle**: 9.4.1 (wrapper)
- **AGP**: 9.2.1
- **Kotlin**: 2.2.10
- **Java**: 21 (via Foojay toolchain resolver in `settings.gradle`)
- **compileSdk/targetSdk**: 36
- **minSdk**: 24

### Key Commands
```bash
# Build both release APKs (as in CI)
./gradlew assembleTempusRelease
./gradlew assembleDegoogledRelease

# Build debug APKs (for testing)
./gradlew assembleTempusDebug
./gradlew assembleDegoogledDebug

# Run unit tests (per flavor)
./gradlew testTempusDebugUnitTest
./gradlew testDegoogledDebugUnitTest

# Run lint (per flavor/variant)
./gradlew lintTempusDebug
./gradlew lintTempusRelease
./gradlew lintDegoogledDebug
./gradlew lintDegoogledRelease

# Run all lint
./gradlew lint

# Run instrumented tests (requires device/emulator)
./gradlew connectedTempusDebugAndroidTest
./gradlew connectedDegoogledDebugAndroidTest

# Clean
./gradlew clean
```

### Build Notes
- Uses **version catalog** (`gradle/libs.versions.toml`) for dependency management
- **ProGuard/R8** enabled for release builds (`minifyEnabled`, `shrinkResources`)
- **Foojay resolver** downloads JDK 21 automatically (no system Java needed)
- Generates **universal APKs** (all ABIs in one APK) via `splits.abi`
- Room schema export to `app/schemas/`
- Mapping files generated for release builds (used for crash deobfuscation)

## Architecture
- **Language**: Kotlin (primary), some Java
- **Architecture**: MVVM-ish with Media3/ExoPlayer for playback
- **Key libs**: Room (DB), Retrofit/OkHttp (network), Media3/ExoPlayer (media), Glide (images), Material3
- **Flavors**: `tempus` (Media3 Cast) vs `degoogled` (no Cast)
- **Main package**: `com.eddyizm.tempus` (namespace), app IDs differ by flavor

## Testing
- **Unit tests**: JUnit 4 + Mockito + MockK (run via `test*UnitTest` tasks)
- **Instrumented tests**: AndroidX Test + Espresso (run via `connected*AndroidTest`)
- **No CI test execution** currently - tests run locally only
- Test configs in `app/build.gradle`: `testOptions.unitTests.returnDefaultValues = true`

## CI / Release Process
- **Prerelease** (`.github/workflows/github_prerelease.yml`): Triggered on `v*-dev*` tags, builds debug APKs, signs with release keystore
- **Release** (`.github/workflows/github_release.yml`): Triggered on `v*` tags (non-dev), builds both release flavors, signs, creates GitHub release with APKs + ProGuard mapping files (gzipped)
- **Signing**: Uses `r0adkll/sign-android-release` action with keystore from secrets
- **Java**: Zulu JDK 21 in CI

## Key Files
- `app/build.gradle` - Main build config, flavors, dependencies
- `gradle/libs.versions.toml` - Version catalog (all versions here)
- `settings.gradle` - Plugin management, Foojay resolver
- `app/proguard-rules.pro` - ProGuard rules (Retrofit, exceptions, line numbers)
- `bin/build.sh` - FFmpeg AAR build script (for custom decoder)

## Contributing Notes (from CONTRIBUTING.md)
- PRs against `development` branch
- Include before/after screenshots for UI changes
- Tests exist, but CI does not execute them; run the flavor-specific unit-test tasks locally.
- Update docs (`USAGE.md`) with changes
- Crash logs are obfuscated in release; deobfuscate with mapping.txt:
  ```bash
  $ANDROID_HOME/cmdline-tools/latest/bin/retrace app/build/outputs/mapping/tempusRelease/mapping.txt stack_error_transcript.txt
  ```

## Common Tasks

| Task | Command |
|------|---------|
| Build debug APK (tempus) | `./gradlew assembleTempusDebug` |
| Build release APK (both) | `./gradlew assembleTempusRelease assembleDegoogledRelease` |
| Run unit tests (tempus) | `./gradlew testTempusDebugUnitTest` |
| Run lint (all) | `./gradlew lint` |
| Clean build | `./gradlew clean` |
| Generate lint baseline | `./gradlew updateLintBaseline` |

## Gotchas
- **Two app IDs**: `com.eddyizm.tempus` vs `com.eddyizm.degoogled.tempus` - debug adds `.debug` suffix
- **Media3 Cast** only in `tempus` flavor (`tempusImplementation libs.media3.cast`)
- **FFmpeg decoder** is a local AAR (`libs/lib-decoder-ffmpeg-release.aar`), built separately via `bin/build.sh`
- **Room schemas** committed to `app/schemas/` - update on schema changes
- **No tests in CI** - run locally before PR
- **Java 21 required** (managed by Foojay in Gradle)

## Proguard mapping for Release

To deobfuscate crash logs:
```bash
$ANDROID_HOME/cmdline-tools/tools/bin/retrace app/build/outputs/mapping/tempusRelease/mapping.txt stack_error_transcript.txt
```

### Development Guidelines

1. **Testing**: Manual testing on physical devices is required - avoid VM testing for network/foreground service features
2. **Database Integrity**: `isDownloaded()` must stay authoritative (Media3 index + Room DB row); external deletes must purge the Media3 index via `DownloaderManager.remove(...)`.
3. **Notification UX**: Single notification with correct actions, tap opens app to queue fragment
4. **Cross-Flavour**: Test on both `tempus` and `degoogled` flavors as they have different capabilities

Skills provide specialized instructions and workflows for specific tasks.
Use the skill tool to load a skill when a task matches its description.
<available_skills>
  <skill>
    <name>customize-opencode</name>
    <description>Use ONLY when the user is editing or creating opencode's own configuration: opencode.json, opencode.jsonc, files under .opencode/, or files under ~/.config/opencode/. Also use when creating or fixing opencode agents, subagents, skills, plugins, MCP servers, or permission rules. Do not use for the user's own application code, or for any project that is not configuring opencode itself.</description>
    <location>&lt;built-in&gt;</location>
  </skill>
</available_skills>

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
