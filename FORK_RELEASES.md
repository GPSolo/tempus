# Queue-enabled fork releases

Releases live at https://github.com/GPSolo/tempus/releases.

## Version and source policy

- Follow **stable upstream releases only**, with a **`-queue` suffix**: upstream
  `v4.31.0` becomes fork `v4.31.0-queue`. Existing upstream tags are not moved.
- Build this fork's `main`, never copy upstream APKs or build the upstream tag alone.
  Require the upstream release commit and original fork queue commit to be ancestors
  of the build. Also require the queue regression tests to exist.
- Require app `versionName` and `versionCode` to match the upstream release's Gradle
  metadata, so a later development version cannot be mislabeled as an older release.
  App IDs and version metadata stay unchanged; the GitHub release tag has the suffix.
- Test both flavors, build universal **Tempus** and **Degoogled** release APKs, sign and
  verify them, and publish with checksums and compressed R8 mappings. No Play Store
  bundle or development prereleases are published by this fork automation.
- Include the exact fork and upstream source commits in release notes. Existing
  releases (including drafts) are skipped, not overwritten. If a matching fork tag
  already points elsewhere, fail rather than move it or attach mismatched APKs.

## Automation

`.github/workflows/fork-release.yml` runs daily at **06:53 UTC**, or manually via
**Actions → Fork stable release → Run workflow** on `main`. It checks the latest
stable upstream release, not the entire historical release catalogue.

The upstream sync PR still needs human review/merge first. If the stable release
commit has not reached fork `main`, publishing waits for a later run. If `main` has
already advanced to different version metadata, publishing waits for manual review;
it does not rewrite version numbers or tag the wrong version. After merging a sync
PR, run the release workflow manually or wait for its next daily check.

Builds have no signing secrets. A separate publishing job downloads the build's
artifacts, signs/verifies them without running source code or Gradle, and publishes
to GitHub. Its credentials never go into the APK or source repository. The inherited
upstream release/prerelease workflows are restricted to `eddyizm/tempus` to prevent
duplicate fork releases.

Check the Actions logs for failures. If a failed upload left a draft/tag, review its
commit and assets manually before retrying; the workflow will not overwrite them.
Scheduled Actions may be disabled by GitHub after 60 days of repository inactivity.

**No AI models or inference services are invoked**, including free models. Only
standard public-repository Linux runners and normal build/release tools are used.

## Signing and installation

GitHub secrets: `FORK_KEYSTORE_BASE64`, `FORK_KEYSTORE_PASSWORD`, `FORK_KEY_ALIAS`.
Use the same dedicated fork key for every future release; losing it breaks the
Android update path for installed fork APKs.

Signing certificate SHA-256 fingerprint:

```text
6B:D1:61:AF:89:01:64:F0:F5:7F:C8:2B:3B:D1:92:EC:75:F9:56:50:B9:D9:97:6C:CA:B1:71:59:CA:4F:F3:BE
```

A protected local recovery copy is in
`/home/gp/.local/share/tempus-release-signing/` (`fork-release.p12` and
`credentials.json`). **Copy this directory into a secure offline backup. Never
commit or share its contents.** GitHub secret values cannot be downloaded later.

The fork is **not signed by upstream**. Back up app settings/data and uninstall the
upstream-signed app before installing the corresponding fork flavor. This can remove
app-local downloads and settings. Future fork releases signed with this same key
can update in place. Debug installs have separate `.debug` package IDs.

Automated tests do not replace manual on-device verification of FIFO order, shuffle,
and repeated queue right-swipes.
