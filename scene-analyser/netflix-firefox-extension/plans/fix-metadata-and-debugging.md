# Plan: Fix Metadata Application, Episode Detection, and Debug Observability

## Overview

The extension captures BIF and subtitle assets but frequently fails to save them to properly-named folders. Analysis of debug logs from real Netflix sessions reveals three root causes:

1. **Silent error swallowing** — `finalizeRequest` errors are caught and logged to console only (line 996), so metadata application failures are invisible in saved debug logs. This makes all other bugs nearly impossible to diagnose.

2. **Metadata application failures** — Sessions show `metadataParsed: true` but no `metadata_applied` or `metadata_skipped` event follows (e.g. watch-70212577, watch-70143170). This means `applyMetadataToSession` throws an unhandled exception after the `request_completed` debug event is written. Assets accumulate in `pendingAssets` but never flush because `flushSessionAssets` requires `session.metadata` to be set (line 708).

3. **TV shows misidentified as movies** — Gossip Girl (a TV series) is detected as `kind: "movie"` because `parseNetflixMemberApiMetadata` requires explicit `showTitle`/`seriesTitle` keys or season/episode numbers to detect episode signals. Netflix's memberapi often puts the show title only inside nested `show`/`series` container objects, which `buildHeuristicCandidate` doesn't inspect, and `buildCombinedCandidate` uses only indirectly via `collectShowContainerTitles`.

4. **licensedmanifest never parses** — Both `memberapi/metadata` and `licensedmanifest` are routed through `parseNetflixMemberApiMetadata`, but `licensedmanifest` has a completely different payload structure (DRM manifest, not title metadata), so parsing always returns null or a meaningless result.

5. **Debug noise** — The global debug log has 3000 events, most of which are `requestKind: "ignored"` CDN range requests. Useful events like `metadata_applied`, `session_started`, `session_closed` are drowned out.

## Phases

### Phase 1: Error Visibility and Debug Quality

**Goal:** Make all errors visible in saved debug logs so subsequent phases can be diagnosed from captures alone.

#### Files: `background.js`

- **Wrap `finalizeRequest` body in try/catch** (line 883-908): catch errors and write a `"finalize_error"` debug event with `error.message` and `error.stack` to the session (or global if session unavailable). Re-throw after logging so the outer `.catch()` still fires for console output.

- **Add error boundary in `processMetadataCapture`** (line 799-829): wrap the `await applyMetadataToSession(...)` call in try/catch, logging a `"metadata_apply_error"` debug event with the error message. This ensures the specific failure point is recorded even if `applyMetadataToSession` throws.

- **Add error boundary in `processBifCapture`** and **`processSubtitleCapture`**: same pattern — catch and log `"asset_capture_error"` before re-throwing.

- **Reduce debug noise**: In `appendSessionDebugEvent`, skip writing to `globalDebugEvents` for events with `requestKind: "ignored"`. Keep them in per-session logs but not in the global log. This makes the global debug log actionable.

- **Add `metadata_attempt` debug event**: In `processMetadataCapture`, right before calling `applyMetadataToSession`, log a `"metadata_attempt"` event with key fields from `parsedMetadata` (kind, videoId, showTitle, movieTitle, episodeTitle). This creates a before/after trail: `request_completed` → `metadata_attempt` → `metadata_applied`/`metadata_skipped`.

#### Files: `lib/metadata_parser.js`

- No changes in this phase.

#### Tests:

- No new test files in this phase (error boundaries are structural, not logic-testable in node:test without browser globals).

#### Expected outcome:
- Every metadata parsing + application attempt leaves a full trail in debug events
- Errors during finalization are recorded in debug JSON, not just console
- Global debug log is ~5-10x smaller and focused on actionable events

---

### Phase 2: Fix Metadata Application to Sessions

**Goal:** Ensure `session.metadata` gets set when `parseNetflixMemberApiMetadata` returns a valid result.

#### Investigation (Phase 1 prerequisite):

Phase 1's error boundaries will reveal the exact exception. However, based on code analysis, the likely candidates are:

- **`persistTabState` in `appendSessionDebugEvent` (line 321)** could fail if the session state exceeds `browser.storage.local` quota limits. The `processMetadataCapture` function calls `appendSessionDebugEvent` (line 802-808), which calls `persistTabState`, which serializes the entire tab state including all session debug events. If this throws, the subsequent `applyMetadataToSession` call on line 821 would never execute.
- **`applySeriesHintToMetadata` (line 589)** accesses `tabState.seriesHintPending` which should exist after the session lifecycle fix, but might be `undefined` on old stored states that were persisted before the field was added.

#### Files: `background.js`

- **Guard `appendSessionDebugEvent` against storage failures**: If `persistTabState` throws inside `appendSessionDebugEvent`, catch the error, log it to console, but don't let it prevent the caller from continuing. The debug event is already pushed to the in-memory array; the persist failure shouldn't block metadata application.

- **Guard `applySeriesHintToMetadata` against missing fields**: Ensure `tabState.seriesHintPending`, `tabState.seriesTitleHint`, etc. default to safe values if undefined.

- **Handle `flushSessionAssets` when session closes with pending assets but null metadata**: Currently line 708 requires `Boolean(session.metadata) || (session.closed && session.openRequestCount === 0)`. When a session closes with assets but no metadata, assets ARE flushed (because `closed` is true), but they go to `watch-XXXXX/` folders. This is actually correct fallback behavior — the bug is that metadata never gets applied in the first place.

#### Tests:

- Add test verifying that `processMetadataCapture` flow doesn't lose metadata when `persistTabState` fails (may need to mock at the unit level).

#### Expected outcome:
- `session.metadata` is reliably set when memberapi returns valid metadata
- Assets flush to properly-named folders instead of `watch-XXXXX/`

---

### Phase 3: Improve Episode Detection in Metadata Parser

**Goal:** Correctly identify TV episodes vs. movies from Netflix memberapi responses.

#### Files: `lib/metadata_parser.js`

- **Add `type`/`entityType` field detection to `buildHeuristicCandidate`**: Netflix memberapi payloads contain explicit type markers like `"type": "show"`, `"type": "series"`, `"entityType": "Episode"`. Add these to the episode signal detection:
  ```
  const TYPE_KEYS = ["type", "entityType", "__typename"];
  const EPISODE_TYPE_VALUES = ["episode", "show", "series", "tvseries", "miniseries"];
  ```
  Check if `node[typeKey]` matches an episode-type value and include that as an episode signal.

- **Improve `buildCombinedCandidate` show detection**: Currently `collectShowContainerTitles` finds titles inside `show`/`series`/`parent` containers, and `buildCombinedCandidate` uses `showContainerTitles[0]` as the show title. But the episode signal check on line 243 only fires when `showTitle !== mainTitle`. If the show container title equals the main title (which happens for first-listed episodes), the content gets classified as a movie. Fix: if `showContainerTitles.length > 0`, set `hasEpisodeSignals = true` regardless of whether the titles differ — the presence of a show container IS an episode signal.

- **Add `seasons`/`episodes` array detection**: If the payload contains keys like `"seasons"`, `"episodes"`, `"numSeasons"`, `"numberOfEpisodes"`, this is a series. Add these as episode signals.

#### Files: `tests/metadata_parser.test.js`

- Add test cases for:
  - A memberapi payload with nested `show` container containing a title
  - A payload with `"type": "show"` explicit marker
  - A payload with `numSeasons` or `seasons` array
  - Gossip Girl-like payload where only a single title field exists but show containers are present

#### Expected outcome:
- TV series like Gossip Girl correctly identified as episodes with `showTitle` set
- `buildTitleSlug` generates episode-style slugs (e.g. `gossip-girl-s01e01-pilot`)

---

### Phase 4: Stop Parsing licensedmanifest as Metadata

**Goal:** Stop wasting effort parsing DRM manifests and reduce false `metadataParsed: false` noise.

#### Files: `background.js`

- **Separate `licensedmanifest` classification**: Change `classifyRequestFromUrl` and `classifyRequestFromHeaders` to return a new `REQUEST_KIND_LICENSED_MANIFEST` constant instead of `REQUEST_KIND_METADATA` for licensedmanifest URLs.

- **Skip body capture for licensedmanifest**: In `handleBeforeRequest`, don't create a filter for `REQUEST_KIND_LICENSED_MANIFEST`. Log a `headers_received` event for observability but don't capture the response body. The licensedmanifest responses are 75-160KB of DRM data that we never successfully parse.

- Alternatively, the simpler approach: just remove `matcherApi.isLicensedManifestUrl(details.url)` from the metadata classification in `classifyRequestFromUrl` (line 490) and `classifyRequestFromHeaders` (line 506). This stops capturing licensedmanifest responses entirely. They still appear in `headers_received` events as `"ignored"`.

#### Tests:

- Update any existing tests that reference licensedmanifest classification if needed.

#### Expected outcome:
- No more `metadataParsed: false` noise from licensedmanifest
- ~75-160KB less memory per session (no longer buffering DRM response bodies)
- Debug logs cleaner

## Notes

- Phase 1 is the highest priority — without error visibility, we're guessing at root causes
- Phase 2 depends on Phase 1 output: the exact exception will confirm whether it's a storage quota issue, a field access issue, or something else
- Phase 3 and Phase 4 are independent of each other and can be done in either order
- All phases must preserve the extension's passive behavior: no request/response modification
- Run `node --test tests/*.test.js` and `node --check background.js` after each phase
