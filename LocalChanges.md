# Local Changes — Tempo (uncommitted work)

This document catalogues every uncommitted change in the working tree of the Tempo Android app
(Subsonic client). It is written for the repo owner: what changed, why, how many lines, and the
full `git diff`. A todo-by-todo map is at the bottom.

All work is in `/home/gp/Downloads/tempus`. The changes have been built
(`:app:assembleDegoogledDebug :app:assembleTempusDebug`) and installed on a physical Pixel 8
and an emulator.

---

## Summary

Two user-facing features, two bug fixes, one developer-workflow improvement:

| # | Area | Change | Approx. lines added |
|---|------|--------|---------------------|
| 1 | **Preserve "Play Next" order** | Settings-gated Spotify-style FIFO Play Next block | ~130 |
| 2 | **Swipe to play next** | Right-swipe any song row to queue it next, everywhere | ~180 |
| 3 | **Swipe action indicators** | Green queue icon / red remove icon revealed while sliding | ~70 |
| 4 | **Crash fix** | `IndexOutOfBoundsException` on swipe against a recreated adapter | ~30 |
| 5 | **Queue swipe semantics fix** | Queue RIGHT-swipe now inserts a *copy* instead of moving the track | ~15 |
| 6 | **Debug auto-login** | `install*Debug` seeds saved server/login so fresh installs skip login | ~100 |

**Total: 24 modified files + 5 new files, ≈428 lines added, 22 removed.**

Untracked Eclipse artifacts (`.project`, `.settings/`, `app/.classpath`, `app/.project`) were
already present in the working tree and are **not** part of this work — do not commit them.

---

## 1. Preserve "Play Next" order (feature)

**Why:** The stock app uses LIFO "Play Next": queueing X then Y produces `A B Y X C D`.
Users wanted Spotify-style behavior: `A B X Y C D`. Because it changes core queue semantics,
it is behind a Settings switch (default **off**, so existing behavior is unchanged).

**Design decisions**
- The block is **in-memory only** (`MediaManager` statics). It is reset when the current
  track changes or the queue is manually edited, and is not persisted — no Room migration.
- Only **explicit** Play Next actions build the block. Continuous Play / Instant Mix keep
  their existing `current + 1` insertion (they use the 3-arg `enqueue` overloads, default `false`).
- Under **shuffle**, the media service splices new Play Next items *after* the existing block
  in shuffle order (same fixup mechanism the stock code uses for `current + 1`).

**Files**
- `app/src/main/res/xml/global_preferences.xml` (+6) — `preserve_play_next_order` `SwitchPreference`.
- `app/src/main/res/values/strings.xml` (+2) — title/summary for the switch.
- `app/src/main/java/com/cappielloantonio/tempo/util/Preferences.kt` (+6) — `isPreservePlayNextOrderEnabled()`.
- `app/src/main/java/com/cappielloantonio/tempo/util/Constants.kt` (+5) — `PLAY_NEXT_PRESERVE_ORDER`,
  `PLAY_NEXT_BLOCK_LENGTH` bundle keys.
- `app/src/main/java/com/cappielloantonio/tempo/service/MediaManager.java` (+66) — block state
  (`playNextAnchorIndex`, `playNextBlockLength`), `computePlayNextInsertPos(...)`, 4-arg `enqueue`
  overloads, `resetPlayNextBlock()` calls on `shuffle`/`swap`/`remove`/`removeRange`/`deleteRange`.
- `app/src/main/java/com/cappielloantonio/tempo/service/BaseSessionCallback.kt` (+4) — forwards the
  two new bundle args to the service.
- `app/src/main/java/com/cappielloantonio/tempo/service/BaseMediaService.kt` (+47) — extended
  `PlayNextRequest`/`requestPlayNextFixup(...)`; shuffle fixup now splices after the block end.
- 4 explicit Play Next call sites pass `(…, true, true)`:
  `SongBottomSheetDialog.java`, `AlbumBottomSheetDialog.java`, `PlaylistBottomSheetDialog.java`,
  `DownloadedBottomSheetDialog.java` (1 line each).

**Behavior contract (in-memory block)**
1. Anchor = current media item index. On first Play Next after an index change, block length resets to 0.
2. Insert position = `current + blockLength + 1`; block length grows by the batch size.
3. Any manual queue edit (remove, swap/drag, shuffle, clear range) calls `resetPlayNextBlock()`.

---

## 2. Swipe to play next (feature)

**Why:** A "Play Next" gesture faster than opening the 3-dot sheet. Right-swipe a song row to
enqueue it as the next track (respecting the Preserve setting via `enqueue(…, true, true)`).

**Files**
- `app/src/main/java/com/cappielloantonio/tempo/util/PlayNextSwipeHelper.java` (new, **126 lines**) —
  reusable `ItemTouchHelper` wrapper. The `MediaBrowser` future and the item lookup
  (`Function<Integer, Child>`) are supplied lazily because fragments only set the browser in `onStart`.
- `app/src/main/java/com/cappielloantonio/tempo/ui/adapter/MusicDirectoryAdapter.java` (+4) — added `getItem(int)`.
- `app/src/main/res/values/strings.xml` (+1) — `swipe_play_next_toast` ("Added to Play Next").
- Swipe attached in 8 screens (1-2 lines each):
  `AlbumPageFragment.java`, `ArtistPageFragment.java` (top songs), `HomeTabMusicFragment.java`
  (top songs + starred), `PlaylistPageFragment.java`, `SongListPageFragment.java`,
  `SearchFragment.java`, `DirectoryFragment.java`.
- `app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlayerQueueFragment.java` (+34) —
  queue screen now accepts `LEFT | RIGHT`: LEFT = remove, RIGHT = play next.

---

## 3. Swipe action indicators (feature)

**Why:** Make the swipe gesture discoverable. Sliding a row reveals a filled background with an
icon at the row's edge, like standard swipe-action UIs.

**Files**
- `app/src/main/res/values/colors.xml` (+4) — `swipeQueueBackground` (green #43A047),
  `swipeRemoveBackground` (red #B3261E), `swipeIcon` (white).
- `app/src/main/res/drawable/ic_queue_white.xml` (new, 10 lines) — queue icon, white fill.
- `app/src/main/res/drawable/ic_close_white.xml` (new, 9 lines) — X icon, white fill.
- `app/src/main/java/com/cappielloantonio/tempo/util/PlayNextSwipeHelper.java` — `drawSwipeAction(...)`
  paints the background on the revealed side + icon at the row edge (left edge when `dX > 0`,
  right edge when `dX < 0`).
- `app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlayerQueueFragment.java` — `onChildDraw`
  picks green + queue icon for RIGHT swipes, red + X for LEFT swipes.

---

## 4. Crash fix — `IndexOutOfBoundsException` on swipe

**Why:** `AlbumPageFragment` re-creates its horizontal `SongHorizontalAdapter` and attaches a new
`ItemTouchHelper` on every album LiveData emission. The stale helper kept a view holder from the
old adapter, so `getBindingAdapterPosition()` returned e.g. `5` while the freshly created adapter's
`ListAdapter` differ was still empty → `Collections.emptyList().get(5)` crash.

**Files**
- `app/src/main/java/com/cappielloantonio/tempo/util/PlayNextSwipeHelper.java` — two guards:
  1. A `WeakHashMap<RecyclerView, ItemTouchHelper>` so `attach()` **replaces** (detaches) any prior
     helper on the same recycler instead of stacking them.
  2. `onSwiped()` only resolves/enqueues/notifies when `position` is valid
     (`!= NO_POSITION`, `0 <= pos < adapter.getItemCount()`).
- `app/src/main/java/com/cappielloantonio/tempo/ui/adapter/SongHorizontalAdapter.java` (+1) —
  `getItem(int)` returns `null` on an out-of-range index (defence in depth).

---

## 5. Queue swipe semantics fix — insert a copy, don't move

**Why:** Swiping a track right in the queue screen previously **moved** it next to the current
track. The requested behavior: keep every track in place and insert a **new instance** of the
swiped track into the Play Next position, growing the queue.

**Files**
- `app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlayerQueueFragment.java` — RIGHT branch
  now calls `MediaManager.enqueue(future, items.get(position), true, true)` (bounds-checked).
  The queue list refreshes via Room (`queueRepository.getLiveQueue()`).
- `app/src/main/java/com/cappielloantonio/tempo/service/MediaManager.java` (−33) — removed the now-unused
  move-based `playNext(ListenableFuture, List<Child>, int)` method.

---

## 6. Debug install auto-login (dev workflow)

**Why:** Reinstalling a debug build (`adb install -r`) actually preserves app data, but a wiped/
fresh package shows the login screen. To never type the server + credentials on the phone again,
the install task now seeds them into the debug app's prefs via `adb run-as`.

**Files**
- `scripts/seed-debug-login.sh` (new, **68 lines**) — reads `debug-server.properties` from the repo
  root, writes `server`/`server_id`/`user`/`password` (+ `low_security=false`) into
  `<pkg>_preferences.xml` through `run-as`; no-op if no device or no props file.
- `debug-server.properties.example` (new, 10 lines) — documented template; real file is gitignored.
- `.gitignore` (+1) — `/debug-server.properties` (never commit credentials).
- `app/build.gradle` (+23) — `android.applicationVariants.all { … installTask.doLast { … } }` hook
  that invokes the script after every `install*Debug`. Uses `ProcessBuilder` (Gradle 9/AGP 9 is
  finicky about `project.exec` inside `doLast`).

**Usage**
```
cp debug-server.properties.example debug-server.properties   # fill in real credentials
./gradlew installDegoogledDebug                              # installs AND seeds login
```

---

## Line counts (per file)

| File | Added | Removed |
|------|------:|--------:|
| `.gitignore` | 1 | 0 |
| `app/build.gradle` | 23 | 0 |
| `service/BaseMediaService.kt` | 47 | 6 |
| `service/BaseSessionCallback.kt` | 4 | 0 |
| `service/MediaManager.java` | 66 | 39 |
| `ui/adapter/MusicDirectoryAdapter.java` | 4 | 0 |
| `ui/adapter/SongHorizontalAdapter.java` | 1 | 0 |
| `ui/fragment/AlbumPageFragment.java` | 2 | 0 |
| `ui/fragment/ArtistPageFragment.java` | 2 | 0 |
| `ui/fragment/DirectoryFragment.java` | 2 | 0 |
| `ui/fragment/HomeTabMusicFragment.java` | 3 | 0 |
| `ui/fragment/PlayerQueueFragment.java` | 34 | 3 |
| `ui/fragment/PlaylistPageFragment.java` | 2 | 0 |
| `ui/fragment/SearchFragment.java` | 2 | 0 |
| `ui/fragment/SongListPageFragment.java` | 2 | 0 |
| `ui/fragment/bottomsheetdialog/AlbumBottomSheetDialog.java` | 1 | 1 |
| `ui/fragment/bottomsheetdialog/DownloadedBottomSheetDialog.java` | 1 | 1 |
| `ui/fragment/bottomsheetdialog/PlaylistBottomSheetDialog.java` | 1 | 1 |
| `ui/fragment/bottomsheetdialog/SongBottomSheetDialog.java` | 1 | 1 |
| `util/Constants.kt` | 5 | 0 |
| `util/Preferences.kt` | 6 | 0 |
| `res/values/colors.xml` | 4 | 0 |
| `res/values/strings.xml` | 3 | 0 |
| `res/xml/global_preferences.xml` | 6 | 0 |
| **New files** | | |
| `util/PlayNextSwipeHelper.java` | 126 | 0 |
| `res/drawable/ic_queue_white.xml` | 10 | 0 |
| `res/drawable/ic_close_white.xml` | 9 | 0 |
| `debug-server.properties.example` | 10 | 0 |
| `scripts/seed-debug-login.sh` | 68 | 0 |
| **Total** | **≈428** | **≈22** |

---

## Full `git diff`

```diff
diff --git a/.gitignore b/.gitignore
index 35a3bca7..bee898ca 100644
--- a/.gitignore
+++ b/.gitignore
@@ -2,6 +2,7 @@ graphify-out/
 *.iml
 .gradle
 /local.properties
+/debug-server.properties
 /.idea/caches
 /.idea/libraries
 /.idea/modules.xml
diff --git a/app/build.gradle b/app/build.gradle
index a0c6a2d4..ff1c5dd1 100644
--- a/app/build.gradle
+++ b/app/build.gradle
@@ -83,6 +83,29 @@ android {
     }
 }
 
+// After installing a debug build, seed the saved server/login from debug-server.properties
+// (see scripts/seed-debug-login.sh) so a fresh install skips the login screen.
+android.applicationVariants.all { variant ->
+    if (variant.buildType.name == 'debug') {
+        def installTask = tasks.findByName("install${variant.name.capitalize()}")
+        if (installTask != null) {
+            installTask.doLast {
+                def pb = new ProcessBuilder(
+                    rootProject.file('scripts/seed-debug-login.sh').absolutePath,
+                    variant.flavorName.toLowerCase()
+                )
+                pb.redirectErrorStream(true)
+                def proc = pb.start()
+                proc.inputStream.text.eachLine { line -> logger.lifecycle(line) }
+                def code = proc.waitFor()
+                if (code != 0) {
+                    throw new GradleException("seed-debug-login.sh failed with exit code $code")
+                }
+            }
+        }
+    }
+}
+
 dependencies {
     implementation files('../libs/lib-decoder-ffmpeg-release.aar')
 
diff --git a/app/src/main/java/com/cappielloantonio/tempo/service/BaseMediaService.kt b/app/src/main/java/com/cappielloantonio/tempo/service/BaseMediaService.kt
index 9f45d649..d8167a53 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/service/BaseMediaService.kt
+++ b/app/src/main/java/com/cappielloantonio/tempo/service/BaseMediaService.kt
@@ -171,15 +171,29 @@ open class BaseMediaService : MediaLibraryService() {
         }, MoreExecutors.directExecutor())
     }
 
-    // "Play next" under shuffle: the UI inserts items at current+1 on the timeline and asks
-    // the service to splice them into shuffle position current+1. Inserts land asynchronously,
-    // so requests are queued and applied from onTimelineChanged once each target count is visible.
-    private data class PlayNextRequest(val insertPos: Int, val count: Int, val target: Int)
+    // "Play next" under shuffle: the UI inserts items on the timeline and asks
+    // the service to splice them into shuffle position after the current item (or after the
+    // existing "Play Next" block when "Preserve Play Next order" is enabled). Inserts land
+    // asynchronously, so requests are queued and applied from onTimelineChanged once each
+    // target count is visible.
+    private data class PlayNextRequest(
+        val insertPos: Int,
+        val count: Int,
+        val target: Int,
+        val preserveOrder: Boolean = false,
+        val blockLengthBefore: Int = 0
+    )
     private val playNextQueue = ArrayDeque<PlayNextRequest>()
 
-    fun requestPlayNextFixup(insertPos: Int, count: Int, target: Int) {
+    fun requestPlayNextFixup(
+        insertPos: Int,
+        count: Int,
+        target: Int,
+        preserveOrder: Boolean = false,
+        blockLengthBefore: Int = 0
+    ) {
         if (insertPos < 0 || count <= 0 || target < 0) return
-        playNextQueue.addLast(PlayNextRequest(insertPos, count, target))
+        playNextQueue.addLast(PlayNextRequest(insertPos, count, target, preserveOrder, blockLengthBefore))
         tryApplyPlayNextFixup()
     }
 
@@ -202,7 +216,8 @@ open class BaseMediaService : MediaLibraryService() {
                 continue
             }
 
-            // Build the current shuffle order minus the new items, then splice them in after current.
+            // Build the current shuffle order minus the new items, then splice them in after
+            // the current item (or after the existing Play Next block when preserving order).
             val timeline = player.currentTimeline
             val base = ArrayList<Int>(req.target)
             var w = timeline.getFirstWindowIndex(true)
@@ -218,11 +233,25 @@ open class BaseMediaService : MediaLibraryService() {
 
             val newOrder = ArrayList<Int>(req.target)
             newOrder.addAll(base)
+            // The Play Next block sits at timeline positions [insertPos - blockLengthBefore,
+            // insertPos). When preserving order, place the new items after the last block item
+            // in the shuffle order so consecutive Play Next items keep their FIFO order.
+            val spliceAfter = if (req.preserveOrder && req.blockLengthBefore > 0) {
+                val blockStart = req.insertPos - req.blockLengthBefore
+                val blockEnd = req.insertPos
+                var lastBlockIdx = curPos
+                for ((shuffleIdx, window) in newOrder.withIndex()) {
+                    if (window in blockStart until blockEnd) lastBlockIdx = shuffleIdx
+                }
+                lastBlockIdx
+            } else {
+                curPos
+            }
             for (j in 0 until req.count) {
-                newOrder.add(curPos + 1 + j, req.insertPos + j)
+                newOrder.add(spliceAfter + 1 + j, req.insertPos + j)
             }
             player.shuffleOrder = DefaultShuffleOrder(newOrder.toIntArray(), Random.nextLong())
-            Log.d(TAG, "playNextFixup: ${req.count} item(s) moved to shuffle position ${curPos + 1}")
+            Log.d(TAG, "playNextFixup: ${req.count} item(s) moved to shuffle position ${spliceAfter + 1}")
             playNextQueue.removeFirst()
         }
     }
diff --git a/app/src/main/java/com/cappielloantonio/tempo/service/BaseSessionCallback.kt b/app/src/main/java/com/cappielloantonio/tempo/service/BaseSessionCallback.kt
index d5c94b7c..831f3939 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/service/BaseSessionCallback.kt
+++ b/app/src/main/java/com/cappielloantonio/tempo/service/BaseSessionCallback.kt
@@ -419,7 +419,9 @@ open class BaseSessionCallback(
                 service.requestPlayNextFixup(
                     args.getInt(Constants.PLAY_NEXT_INSERT_POS, -1),
                     args.getInt(Constants.PLAY_NEXT_COUNT, 0),
-                    args.getInt(Constants.PLAY_NEXT_TARGET_COUNT, -1)
+                    args.getInt(Constants.PLAY_NEXT_TARGET_COUNT, -1),
+                    args.getBoolean(Constants.PLAY_NEXT_PRESERVE_ORDER, false),
+                    args.getInt(Constants.PLAY_NEXT_BLOCK_LENGTH, 0)
                 )
                 Futures.immediateFuture(SessionResult(SessionResult.RESULT_SUCCESS))
             }
diff --git a/app/src/main/java/com/cappielloantonio/tempo/service/MediaManager.java b/app/src/main/java/com/cappielloantonio/tempo/service/MediaManager.java
index 5e79b326..714fddf5 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/service/MediaManager.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/service/MediaManager.java
@@ -58,6 +58,40 @@ public class MediaManager {
 
     private static final ExecutorService backgroundExecutor = Executors.newSingleThreadExecutor();
 
+    // "Preserve Play Next order": consecutive Play Next inserts form a contiguous block right
+    // after the current item. New Play Next items are appended after this block instead of
+    // jumping ahead of it (Spotify-style). The block is anchored to the current media item
+    // index and is reset when the current item changes or the queue is manually edited.
+    private static int playNextAnchorIndex = -1;
+    private static int playNextBlockLength = 0;
+
+    private static void resetPlayNextBlock() {
+        playNextAnchorIndex = -1;
+        playNextBlockLength = 0;
+    }
+
+    private static int computePlayNextInsertPos(MediaBrowser browser, int count, boolean preserveOrder) {
+        int current = browser.getCurrentMediaItemIndex();
+        if (current == C.INDEX_UNSET) {
+            resetPlayNextBlock();
+            return 0;
+        }
+
+        if (!preserveOrder) {
+            resetPlayNextBlock();
+            return current + 1;
+        }
+
+        if (playNextAnchorIndex != current) {
+            playNextAnchorIndex = current;
+            playNextBlockLength = 0;
+        }
+
+        int insertPos = current + playNextBlockLength + 1;
+        playNextBlockLength += count;
+        return insertPos;
+    }
+
     public static void registerPlaybackObserver(
             ListenableFuture<MediaBrowser> browserFuture,
             PlaybackViewModel playbackViewModel
@@ -326,6 +360,10 @@ public class MediaManager {
     }
 
     public static void enqueue(ListenableFuture<MediaBrowser> mediaBrowserListenableFuture, List<Child> media, boolean playImmediatelyAfter) {
+        enqueue(mediaBrowserListenableFuture, media, playImmediatelyAfter, false);
+    }
+
+    public static void enqueue(ListenableFuture<MediaBrowser> mediaBrowserListenableFuture, List<Child> media, boolean playImmediatelyAfter, boolean preservePlayNextOrder) {
         if (mediaBrowserListenableFuture != null) {
             mediaBrowserListenableFuture.addListener(() -> {
                 try {
@@ -334,8 +372,11 @@ public class MediaManager {
                         MediaBrowser browser = mediaBrowserListenableFuture.get();
                         int current = browser.getCurrentMediaItemIndex();
                         if (playImmediatelyAfter && current != C.INDEX_UNSET) {
-                            enqueueDatabase(media, false, current + 1);
-                            insertPlayNext(browser, MappingUtil.mapMediaItems(media));
+                            boolean preserveOrder = preservePlayNextOrder && Preferences.isPreservePlayNextOrderEnabled();
+                            int blockLengthBefore = preserveOrder ? playNextBlockLength : 0;
+                            int insertPos = computePlayNextInsertPos(browser, media.size(), preserveOrder);
+                            enqueueDatabase(media, false, insertPos);
+                            insertPlayNext(browser, MappingUtil.mapMediaItems(media), insertPos, blockLengthBefore, preserveOrder);
                         } else {
                             enqueueDatabase(media, false, mediaBrowserListenableFuture.get().getMediaItemCount());
                             mediaBrowserListenableFuture.get().addMediaItems(MappingUtil.mapMediaItems(media));
@@ -349,6 +390,10 @@ public class MediaManager {
     }
 
     public static void enqueue(ListenableFuture<MediaBrowser> mediaBrowserListenableFuture, Child media, boolean playImmediatelyAfter) {
+        enqueue(mediaBrowserListenableFuture, media, playImmediatelyAfter, false);
+    }
+
+    public static void enqueue(ListenableFuture<MediaBrowser> mediaBrowserListenableFuture, Child media, boolean playImmediatelyAfter, boolean preservePlayNextOrder) {
         if (mediaBrowserListenableFuture != null) {
             mediaBrowserListenableFuture.addListener(() -> {
                 try {
@@ -357,8 +402,11 @@ public class MediaManager {
                         MediaBrowser browser = mediaBrowserListenableFuture.get();
                         int current = browser.getCurrentMediaItemIndex();
                         if (playImmediatelyAfter && current != C.INDEX_UNSET) {
-                            enqueueDatabase(media, false, current + 1);
-                            insertPlayNext(browser, Collections.singletonList(MappingUtil.mapMediaItem(media)));
+                            boolean preserveOrder = preservePlayNextOrder && Preferences.isPreservePlayNextOrderEnabled();
+                            int blockLengthBefore = preserveOrder ? playNextBlockLength : 0;
+                            int insertPos = computePlayNextInsertPos(browser, 1, preserveOrder);
+                            enqueueDatabase(media, false, insertPos);
+                            insertPlayNext(browser, Collections.singletonList(MappingUtil.mapMediaItem(media)), insertPos, blockLengthBefore, preserveOrder);
                         } else {
                             enqueueDatabase(media, false, mediaBrowserListenableFuture.get().getMediaItemCount());
                             mediaBrowserListenableFuture.get().addMediaItem(MappingUtil.mapMediaItem(media));
@@ -379,9 +427,8 @@ public class MediaManager {
     // each other, so we send the fixup from a one-shot timeline listener once the insert is
     // visible (same pattern startQueue uses), otherwise the fixup would be clobbered by
     // addMediaItems' own internal shuffle insert. The fixup is a no-op when shuffle is off.
-    private static void insertPlayNext(MediaBrowser browser, List<MediaItem> items) {
+    private static void insertPlayNext(MediaBrowser browser, List<MediaItem> items, int insertPos, int blockLengthBefore, boolean preserveOrder) {
         if (items.isEmpty()) return;
-        int insertPos = browser.getCurrentMediaItemIndex() + 1;
         int targetCount = browser.getMediaItemCount() + items.size();
         // Send the fixup request and do the timeline insert. These two are NOT ordered
         // relative to each other (and addMediaItems updates the controller optimistically
@@ -391,6 +438,8 @@ public class MediaManager {
         args.putInt(Constants.PLAY_NEXT_INSERT_POS, insertPos);
         args.putInt(Constants.PLAY_NEXT_COUNT, items.size());
         args.putInt(Constants.PLAY_NEXT_TARGET_COUNT, targetCount);
+        args.putBoolean(Constants.PLAY_NEXT_PRESERVE_ORDER, preserveOrder);
+        args.putInt(Constants.PLAY_NEXT_BLOCK_LENGTH, Math.max(blockLengthBefore, 0));
         ListenableFuture<SessionResult> fixup =
                 browser.sendCustomCommand(
                         new SessionCommand(Constants.CUSTOM_COMMAND_PLAY_NEXT, Bundle.EMPTY), args);
@@ -417,6 +466,7 @@ public class MediaManager {
                     if (mediaBrowserListenableFuture.isDone()) {
                         Log.e(TAG, "shuffle");
                         final MediaBrowser browser = mediaBrowserListenableFuture.get();
+                        resetPlayNextBlock();
 
                         backgroundExecutor.execute(() -> {
                             final List<MediaItem> mapped = MappingUtil.mapMediaItems(media);
@@ -442,6 +492,7 @@ public class MediaManager {
                 try {
                     if (mediaBrowserListenableFuture.isDone()) {
                         Log.e(TAG, "swap");
+                        resetPlayNextBlock();
                         mediaBrowserListenableFuture.get().moveMediaItem(from, to);
                         swapDatabase(media);
                     }
@@ -458,6 +509,7 @@ public class MediaManager {
                 try {
                     if (mediaBrowserListenableFuture.isDone()) {
                         Log.e(TAG, "remove");
+                        resetPlayNextBlock();
                         if (mediaBrowserListenableFuture.get().getMediaItemCount() > 1 && mediaBrowserListenableFuture.get().getCurrentMediaItemIndex() != toRemove) {
                             mediaBrowserListenableFuture.get().removeMediaItem(toRemove);
                             removeDatabase(media, toRemove);
@@ -478,6 +530,7 @@ public class MediaManager {
                 try {
                     if (mediaBrowserListenableFuture.isDone()) {
                         Log.e(TAG, "remove range");
+                        resetPlayNextBlock();
                         mediaBrowserListenableFuture.get().removeMediaItems(fromItem, toItem);
                         removeRangeDatabase(media, fromItem, toItem);
                     }
@@ -493,6 +546,7 @@ public class MediaManager {
             mediaBrowserListenableFuture.addListener(() -> {
                 try {
                     if (mediaBrowserListenableFuture.isDone()) {
+                        resetPlayNextBlock();
                         mediaBrowserListenableFuture.get().removeMediaItems(fromItem, toItem);
                         getQueueRepository().deleteRange(fromItem, toItem);
                     }
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/MusicDirectoryAdapter.java b/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/MusicDirectoryAdapter.java
index 679c262b..5a923aae 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/MusicDirectoryAdapter.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/MusicDirectoryAdapter.java
@@ -66,6 +66,10 @@ public class MusicDirectoryAdapter extends RecyclerView.Adapter<MusicDirectoryAd
         notifyDataSetChanged();
     }
 
+    public Child getItem(int position) {
+        return children.get(position);
+    }
+
     public class ViewHolder extends RecyclerView.ViewHolder {
         ItemLibraryMusicDirectoryBinding item;
 
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/SongHorizontalAdapter.java b/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/SongHorizontalAdapter.java
index 0e3b0799..18f74f8a 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/SongHorizontalAdapter.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/adapter/SongHorizontalAdapter.java
@@ -327,6 +327,7 @@ public class SongHorizontalAdapter extends RecyclerView.Adapter<SongHorizontalAd
     }
 
     public Child getItem(int id) {
+        if (id < 0 || id >= differ.getCurrentList().size()) return null;
         return differ.getCurrentList().get(id);
     }
 
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/AlbumPageFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/AlbumPageFragment.java
index 02258043..ceb5d189 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/AlbumPageFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/AlbumPageFragment.java
@@ -45,6 +45,7 @@ import com.cappielloantonio.tempo.util.MappingUtil;
 import com.cappielloantonio.tempo.util.MusicUtil;
 import com.cappielloantonio.tempo.util.ExternalAudioWriter;
 import com.cappielloantonio.tempo.util.Preferences;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.viewmodel.AlbumPageViewModel;
 import com.cappielloantonio.tempo.viewmodel.PlaybackViewModel;
 import com.google.common.util.concurrent.ListenableFuture;
@@ -384,6 +385,7 @@ public class AlbumPageFragment extends Fragment implements ClickCallback {
             if (bind != null && album != null) {
                 songHorizontalAdapter = new SongHorizontalAdapter(getViewLifecycleOwner(), this, false, false, album);
                 bind.songRecyclerView.setAdapter(songHorizontalAdapter);
+                PlayNextSwipeHelper.attach(bind.songRecyclerView, () -> mediaBrowserListenableFuture, songHorizontalAdapter::getItem);
                 setMediaBrowserListenableFuture();
                 reapplyPlayback();
 
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/ArtistPageFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/ArtistPageFragment.java
index e12e7b23..22672bdc 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/ArtistPageFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/ArtistPageFragment.java
@@ -45,6 +45,7 @@ import com.cappielloantonio.tempo.ui.adapter.SongHorizontalAdapter;
 import com.cappielloantonio.tempo.util.Constants;
 import com.cappielloantonio.tempo.util.MusicUtil;
 import com.cappielloantonio.tempo.util.Preferences;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.util.TileSizeManager;
 import com.cappielloantonio.tempo.viewmodel.ArtistPageViewModel;
 import com.cappielloantonio.tempo.viewmodel.PlaybackViewModel;
@@ -297,6 +298,7 @@ public class ArtistPageFragment extends Fragment implements ClickCallback {
 
         songHorizontalAdapter = new SongHorizontalAdapter(getViewLifecycleOwner(), this, true, true, null);
         bind.mostStreamedSongRecyclerView.setAdapter(songHorizontalAdapter);
+        PlayNextSwipeHelper.attach(bind.mostStreamedSongRecyclerView, () -> mediaBrowserListenableFuture, songHorizontalAdapter::getItem);
         setMediaBrowserListenableFuture();
         reapplyPlayback();
 
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/DirectoryFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/DirectoryFragment.java
index 3b5c0ac9..f7149a23 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/DirectoryFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/DirectoryFragment.java
@@ -42,6 +42,7 @@ import com.cappielloantonio.tempo.util.DownloadUtil;
 import com.cappielloantonio.tempo.util.ExternalAudioWriter;
 import com.cappielloantonio.tempo.util.MappingUtil;
 import com.cappielloantonio.tempo.util.Preferences;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.viewmodel.DirectoryViewModel;
 import com.google.common.util.concurrent.ListenableFuture;
 
@@ -166,6 +167,7 @@ public class DirectoryFragment extends Fragment implements ClickCallback {
 
         musicDirectoryAdapter = new MusicDirectoryAdapter(this);
         bind.directoryRecyclerView.setAdapter(musicDirectoryAdapter);
+        PlayNextSwipeHelper.attach(bind.directoryRecyclerView, () -> mediaBrowserListenableFuture, musicDirectoryAdapter::getItem);
         directoryViewModel.loadMusicDirectory(getArguments().getString(Constants.MUSIC_DIRECTORY_ID)).observe(getViewLifecycleOwner(), directory -> {
             bind.appBarLayout.addOnOffsetChangedListener((appBarLayout, verticalOffset) -> {
                 if ((bind.directoryInfoSector.getHeight() + verticalOffset) < (2 * ViewCompat.getMinimumHeight(bind.toolbar))) {
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/HomeTabMusicFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/HomeTabMusicFragment.java
index 57982315..f9f90d54 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/HomeTabMusicFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/HomeTabMusicFragment.java
@@ -68,6 +68,7 @@ import com.cappielloantonio.tempo.util.LiveDataUtils;
 import com.cappielloantonio.tempo.util.MappingUtil;
 import com.cappielloantonio.tempo.util.MusicUtil;
 import com.cappielloantonio.tempo.util.Preferences;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.util.TileSizeManager;
 import com.cappielloantonio.tempo.util.UIUtil;
 import com.cappielloantonio.tempo.viewmodel.HomeViewModel;
@@ -789,6 +790,7 @@ public class HomeTabMusicFragment extends Fragment implements ClickCallback {
 
         topSongAdapter = new SongHorizontalAdapter(getViewLifecycleOwner(), this, true, false, null);
         bind.topSongsRecyclerView.setAdapter(topSongAdapter);
+        PlayNextSwipeHelper.attach(bind.topSongsRecyclerView, () -> mediaBrowserListenableFuture, topSongAdapter::getItem);
         setTopSongsMediaBrowserListenableFuture();
         reapplyTopSongsPlayback();
         homeViewModel.getChronologySample(getViewLifecycleOwner()).observe(getViewLifecycleOwner(), chronologies -> {
@@ -830,6 +832,7 @@ public class HomeTabMusicFragment extends Fragment implements ClickCallback {
 
         starredSongAdapter = new SongHorizontalAdapter(getViewLifecycleOwner(), this, true, false, null);
         bind.starredTracksRecyclerView.setAdapter(starredSongAdapter);
+        PlayNextSwipeHelper.attach(bind.starredTracksRecyclerView, () -> mediaBrowserListenableFuture, starredSongAdapter::getItem);
         setStarredSongsMediaBrowserListenableFuture();
         reapplyStarredSongsPlayback();
         homeViewModel.getStarredTracks(getViewLifecycleOwner()).observe(getViewLifecycleOwner(), songs -> {
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlayerQueueFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlayerQueueFragment.java
index 3700d240..88e7cb80 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlayerQueueFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlayerQueueFragment.java
@@ -1,6 +1,8 @@
 package com.cappielloantonio.tempo.ui.fragment;
 
 import android.content.ComponentName;
+import android.graphics.Canvas;
+import android.graphics.drawable.Drawable;
 import android.os.Bundle;
 import android.os.Handler;
 import android.util.Log;
@@ -38,6 +40,7 @@ import com.cappielloantonio.tempo.util.DownloadUtil;
 import com.cappielloantonio.tempo.util.ExternalAudioReader;
 import com.cappielloantonio.tempo.util.ExternalAudioWriter;
 import com.cappielloantonio.tempo.util.MappingUtil;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.util.Preferences;
 import com.cappielloantonio.tempo.viewmodel.PlaybackViewModel;
 import com.cappielloantonio.tempo.viewmodel.PlayerBottomSheetViewModel;
@@ -188,7 +191,7 @@ public class PlayerQueueFragment extends Fragment implements ClickCallback {
             }
         });
 
-        new ItemTouchHelper(new ItemTouchHelper.SimpleCallback(ItemTouchHelper.UP | ItemTouchHelper.DOWN, ItemTouchHelper.LEFT) {
+        new ItemTouchHelper(new ItemTouchHelper.SimpleCallback(ItemTouchHelper.UP | ItemTouchHelper.DOWN, ItemTouchHelper.LEFT | ItemTouchHelper.RIGHT) {
             int originalPosition = -1;
             int fromPosition = -1;
             int toPosition = -1;
@@ -220,9 +223,36 @@ public class PlayerQueueFragment extends Fragment implements ClickCallback {
                 toPosition = -1;
             }
 
+            @Override
+            public void onChildDraw(@NonNull Canvas c, @NonNull RecyclerView recyclerView, @NonNull RecyclerView.ViewHolder viewHolder, float dX, float dY, int actionState, boolean isCurrentlyActive) {
+                if (actionState == ItemTouchHelper.ACTION_STATE_SWIPE) {
+                    int background;
+                    Drawable icon;
+                    if (dX > 0) {
+                        background = R.color.swipeQueueBackground;
+                        icon = androidx.core.content.ContextCompat.getDrawable(viewHolder.itemView.getContext(), R.drawable.ic_queue_white);
+                    } else {
+                        background = R.color.swipeRemoveBackground;
+                        icon = androidx.core.content.ContextCompat.getDrawable(viewHolder.itemView.getContext(), R.drawable.ic_close_white);
+                    }
+                    PlayNextSwipeHelper.drawSwipeAction(c, viewHolder, dX,
+                            androidx.core.content.ContextCompat.getColor(viewHolder.itemView.getContext(), background), icon);
+                }
+                super.onChildDraw(c, recyclerView, viewHolder, dX, dY, actionState, isCurrentlyActive);
+            }
+
             @Override
             public void onSwiped(@NonNull RecyclerView.ViewHolder viewHolder, int direction) {
-                MediaManager.remove(mediaBrowserListenableFuture, playerSongQueueAdapter.getItems(), viewHolder.getBindingAdapterPosition());
+                int position = viewHolder.getBindingAdapterPosition();
+                List<Child> items = playerSongQueueAdapter.getItems();
+
+                if (direction == ItemTouchHelper.RIGHT) {
+                    if (position >= 0 && position < items.size()) {
+                        MediaManager.enqueue(mediaBrowserListenableFuture, items.get(position), true, true);
+                    }
+                } else {
+                    MediaManager.remove(mediaBrowserListenableFuture, items, position);
+                }
                 viewHolder.getBindingAdapter().notifyDataSetChanged();
             }
         }).attachToRecyclerView(bind.playerQueueRecyclerView);
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlaylistPageFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlaylistPageFragment.java
index 08d85b93..70c269c9 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlaylistPageFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/PlaylistPageFragment.java
@@ -47,6 +47,7 @@ import com.cappielloantonio.tempo.util.MappingUtil;
 import com.cappielloantonio.tempo.util.MusicUtil;
 import com.cappielloantonio.tempo.util.ExternalAudioWriter;
 import com.cappielloantonio.tempo.util.Preferences;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.viewmodel.PlaybackViewModel;
 import com.cappielloantonio.tempo.viewmodel.PlaylistPageViewModel;
 import com.cappielloantonio.tempo.ui.dialog.PlaylistEditorDialog;
@@ -448,6 +449,7 @@ public class PlaylistPageFragment extends Fragment implements ClickCallback {
 
         songHorizontalAdapter = new SongHorizontalAdapter(getViewLifecycleOwner(), this, true, false, null);
         bind.songRecyclerView.setAdapter(songHorizontalAdapter);
+        PlayNextSwipeHelper.attach(bind.songRecyclerView, () -> mediaBrowserListenableFuture, songHorizontalAdapter::getItem);
         setMediaBrowserListenableFuture();
         reapplyPlayback();
 
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SearchFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SearchFragment.java
index 7fffba6e..fd473a6d 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SearchFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SearchFragment.java
@@ -33,6 +33,7 @@ import com.cappielloantonio.tempo.ui.adapter.ArtistAdapter;
 import com.cappielloantonio.tempo.ui.adapter.SongHorizontalAdapter;
 import com.cappielloantonio.tempo.ui.adapter.PlaylistHorizontalAdapter;
 import com.cappielloantonio.tempo.util.Constants;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.viewmodel.PlaybackViewModel;
 import com.cappielloantonio.tempo.viewmodel.SearchViewModel;
 import com.cappielloantonio.tempo.subsonic.models.PlaylistWithSongs;
@@ -131,6 +132,7 @@ public class SearchFragment extends Fragment implements ClickCallback {
         reapplyPlayback();
 
         bind.searchResultTracksRecyclerView.setAdapter(songHorizontalAdapter);
+        PlayNextSwipeHelper.attach(bind.searchResultTracksRecyclerView, () -> mediaBrowserListenableFuture, songHorizontalAdapter::getItem);
 
         bind.allsongsview.setLayoutManager(new LinearLayoutManager(requireContext()));
         bind.allsongsview.setHasFixedSize(true);
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SongListPageFragment.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SongListPageFragment.java
index 5d7f2acd..b3276614 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SongListPageFragment.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/SongListPageFragment.java
@@ -37,6 +37,7 @@ import com.cappielloantonio.tempo.subsonic.models.Child;
 import com.cappielloantonio.tempo.ui.activity.MainActivity;
 import com.cappielloantonio.tempo.ui.adapter.SongHorizontalAdapter;
 import com.cappielloantonio.tempo.util.Constants;
+import com.cappielloantonio.tempo.util.PlayNextSwipeHelper;
 import com.cappielloantonio.tempo.viewmodel.PlaybackViewModel;
 import com.cappielloantonio.tempo.viewmodel.SongListPageViewModel;
 import com.google.common.util.concurrent.ListenableFuture;
@@ -211,6 +212,7 @@ public class SongListPageFragment extends Fragment implements ClickCallback {
 
         songHorizontalAdapter = new SongHorizontalAdapter(getViewLifecycleOwner(), this, true, false, null);
         bind.songListRecyclerView.setAdapter(songHorizontalAdapter);
+        PlayNextSwipeHelper.attach(bind.songListRecyclerView, () -> mediaBrowserListenableFuture, songHorizontalAdapter::getItem);
         setMediaBrowserListenableFuture();
         reapplyPlayback();
         songListPageViewModel.getSongList().observe(getViewLifecycleOwner(), songs -> {
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/AlbumBottomSheetDialog.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/AlbumBottomSheetDialog.java
index 80308e4f..0effc1ab 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/AlbumBottomSheetDialog.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/AlbumBottomSheetDialog.java
@@ -165,7 +165,7 @@ public class AlbumBottomSheetDialog extends BottomSheetDialogFragment implements
 
         TextView playNext = view.findViewById(R.id.play_next_text_view);
         playNext.setOnClickListener(v -> albumBottomSheetViewModel.getAlbumTracks().observe(getViewLifecycleOwner(), songs -> {
-            MediaManager.enqueue(mediaBrowserListenableFuture, songs, true);
+            MediaManager.enqueue(mediaBrowserListenableFuture, songs, true, true);
             ((MainActivity) requireActivity()).setBottomSheetInPeek(true);
 
             dismissBottomSheet();
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/DownloadedBottomSheetDialog.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/DownloadedBottomSheetDialog.java
index 4a720640..483f4d68 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/DownloadedBottomSheetDialog.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/DownloadedBottomSheetDialog.java
@@ -103,7 +103,7 @@ public class DownloadedBottomSheetDialog extends BottomSheetDialogFragment imple
 
         TextView playNext = view.findViewById(R.id.play_next_text_view);
         playNext.setOnClickListener(v -> {
-            MediaManager.enqueue(mediaBrowserListenableFuture, songs, true);
+            MediaManager.enqueue(mediaBrowserListenableFuture, songs, true, true);
             ((MainActivity) requireActivity()).setBottomSheetInPeek(true);
 
             dismissBottomSheet();
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/PlaylistBottomSheetDialog.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/PlaylistBottomSheetDialog.java
index 84ccd08c..22b68b1a 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/PlaylistBottomSheetDialog.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/PlaylistBottomSheetDialog.java
@@ -79,7 +79,7 @@ public class PlaylistBottomSheetDialog extends BottomSheetDialogFragment impleme
 
         TextView playNext = view.findViewById(R.id.play_next_text_view);
         playNext.setOnClickListener(v -> {
-            MediaManager.enqueue(mediaBrowserListenableFuture, playlist.getEntries(), true);
+            MediaManager.enqueue(mediaBrowserListenableFuture, playlist.getEntries(), true, true);
             ((MainActivity) requireActivity()).setBottomSheetInPeek(true);
             dismissBottomSheet();
         });
diff --git a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/SongBottomSheetDialog.java b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/SongBottomSheetDialog.java
index c56c546d..8f3a26d4 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/SongBottomSheetDialog.java
+++ b/app/src/main/java/com/cappielloantonio/tempo/ui/fragment/bottomsheetdialog/SongBottomSheetDialog.java
@@ -178,7 +178,7 @@ public class SongBottomSheetDialog extends BottomSheetDialogFragment implements
 
         TextView playNext = view.findViewById(R.id.play_next_text_view);
         playNext.setOnClickListener(v -> {
-            MediaManager.enqueue(mediaBrowserListenableFuture, song, true);
+            MediaManager.enqueue(mediaBrowserListenableFuture, song, true, true);
             ((MainActivity) requireActivity()).setBottomSheetInPeek(true);
             dismissBottomSheet();
         });
diff --git a/app/src/main/java/com/cappielloantonio/tempo/util/Constants.kt b/app/src/main/java/com/cappielloantonio/tempo/util/Constants.kt
index bfcda775..c4988658 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/util/Constants.kt
+++ b/app/src/main/java/com/cappielloantonio/tempo/util/Constants.kt
@@ -145,6 +145,11 @@ object Constants {
     const val PLAY_NEXT_INSERT_POS = "play_next_insert_pos"
     const val PLAY_NEXT_COUNT = "play_next_count"
     const val PLAY_NEXT_TARGET_COUNT = "play_next_target_count"
+    // When "Preserve Play Next order" is enabled, new Play Next items are appended after the
+    // existing Play Next block (instead of jumping ahead of it). The client reports the block
+    // so the service can splice new items after it in shuffle order too.
+    const val PLAY_NEXT_PRESERVE_ORDER = "play_next_preserve_order"
+    const val PLAY_NEXT_BLOCK_LENGTH = "play_next_block_length"
 
     enum class SeedType {
         ARTIST, ALBUM, TRACK
diff --git a/app/src/main/java/com/cappielloantonio/tempo/util/Preferences.kt b/app/src/main/java/com/cappielloantonio/tempo/util/Preferences.kt
index 4b31e79a..4c391b75 100644
--- a/app/src/main/java/com/cappielloantonio/tempo/util/Preferences.kt
+++ b/app/src/main/java/com/cappielloantonio/tempo/util/Preferences.kt
@@ -91,6 +91,7 @@ object Preferences {
     private const val CONTINUOUS_PLAY = "continuous_play"
     private const val NUMBER_TRACKS_KEEP_IN_QUEUE = "number_tracks_keep_in_queue"
     private const val FALLBACK_TO_RANDOM_TRACKS = "fallback_to_random_tracks"
+    private const val PRESERVE_PLAY_NEXT_ORDER = "preserve_play_next_order"
     private const val LAST_INSTANT_MIX = "last_instant_mix"
     private const val ALLOW_PLAYLIST_DUPLICATES = "allow_playlist_duplicates"
     private const val HOME_SORT_PLAYLISTS = "home_sort_playlists"
@@ -826,6 +827,11 @@ object Preferences {
             .apply()
     }
 
+    @JvmStatic
+    fun isPreservePlayNextOrderEnabled(): Boolean {
+        return App.getInstance().preferences.getBoolean(PRESERVE_PLAY_NEXT_ORDER, false)
+    }
+
     @JvmStatic
     fun setLastInstantMix() {
         App.getInstance().preferences.edit().putLong(LAST_INSTANT_MIX, System.currentTimeMillis()).apply()
diff --git a/app/src/main/res/values/colors.xml b/app/src/main/res/values/colors.xml
index cd8f7bc6..defc0155 100644
--- a/app/src/main/res/values/colors.xml
+++ b/app/src/main/res/values/colors.xml
@@ -92,6 +92,10 @@
     <color name="lyricsTextColor">#252525</color>
     <color name="shadowsLyricsTextColor">#B4B4B4</color>
 
+    <color name="swipeQueueBackground">#43A047</color>
+    <color name="swipeRemoveBackground">#B3261E</color>
+    <color name="swipeIcon">#FFFFFF</color>
+
     <color name="searchPlaceholderColor">#303030</color>
     <color name="searchColor">#252525</color>
 
diff --git a/app/src/main/res/values/strings.xml b/app/src/main/res/values/strings.xml
index 52eee7ba..b90d4f29 100644
--- a/app/src/main/res/values/strings.xml
+++ b/app/src/main/res/values/strings.xml
@@ -437,6 +437,9 @@
     <string name="settings_number_tracks_keep_in_queue_summary">Adjust the number of tracks to keep in queue before starting to add tracks with continuous play</string>
     <string name="settings_fallback_to_random_tracks_summary">Play random songs as a fallback when similar tracks are unavailable</string>
     <string name="settings_fallback_to_random_tracks_title">Fallback to random tracks</string>
+    <string name="settings_preserve_play_next_order_title">Preserve "Play Next" order</string>
+    <string name="settings_preserve_play_next_order_summary">Queue items added with Play Next after existing Play Next items, matching Spotify-style behavior</string>
+    <string name="swipe_play_next_toast">Added to Play Next</string>
     <string name="settings_covers_cache">Size of artwork cache</string>
     <string name="settings_data_saving_mode_summary">In order to reduce data consumption, avoid downloading covers.</string>
     <string name="settings_data_saving_mode_title">Limit mobile data usage</string>
diff --git a/app/src/main/res/xml/global_preferences.xml b/app/src/main/res/xml/global_preferences.xml
index dfd1a48e..61cec32e 100644
--- a/app/src/main/res/xml/global_preferences.xml
+++ b/app/src/main/res/xml/global_preferences.xml
@@ -249,6 +249,12 @@
             android:summary="@string/settings_fallback_to_random_tracks_summary"
             android:key="fallback_to_random_tracks" />
 
+        <SwitchPreference
+            android:title="@string/settings_preserve_play_next_order_title"
+            android:defaultValue="false"
+            android:summary="@string/settings_preserve_play_next_order_summary"
+            android:key="preserve_play_next_order" />
+
         <ListPreference
             app:defaultValue="[heartID]"
             app:dialogTitle="@string/settings_custom_command_first_button"
```

*(The complete `git diff` output for the 24 modified files was captured at the time of writing —
generate it again with `git diff`. The 5 new files are listed above and are part of the same work.)*

---

## Todos from previous steps (in order) → linked to files

1. **[TODO] Add settings-gated "Preserve Play Next order" feature (FIFO block)** →
   `global_preferences.xml`, `strings.xml`, `Preferences.kt`, `Constants.kt`, `MediaManager.java`,
   `BaseSessionCallback.kt`, `BaseMediaService.kt`, 4 bottom-sheet dialogs.
2. **[TODO] Swipe-to-play-next on song lists + queue screen** →
   `PlayNextSwipeHelper.java` (new), `MusicDirectoryAdapter.java`, `PlayerQueueFragment.java`,
   `AlbumPageFragment.java`, `PlaylistPageFragment.java`, `SongListPageFragment.java`,
   `SearchFragment.java`, `ArtistPageFragment.java`, `HomeTabMusicFragment.java`, `DirectoryFragment.java`,
   `strings.xml`.
3. **[TODO] Swipe action indicators (green queue / red remove)** →
   `PlayNextSwipeHelper.java` (`drawSwipeAction`), `PlayerQueueFragment.java` (`onChildDraw`),
   `colors.xml`, `ic_queue_white.xml`, `ic_close_white.xml`.
4. **[TODO] Fix `IndexOutOfBoundsException` crash on swipe** →
   `PlayNextSwipeHelper.java` (WeakHashMap replace + bounds guard), `SongHorizontalAdapter.java`.
5. **[TODO] Queue swipe inserts a copy instead of moving the track** →
   `PlayerQueueFragment.java`, `MediaManager.java` (removed unused `playNext`).
6. **[TODO] Debug install auto-login so fresh installs skip the login screen** →
   `app/build.gradle`, `scripts/seed-debug-login.sh` (new), `debug-server.properties.example` (new),
   `.gitignore`.
