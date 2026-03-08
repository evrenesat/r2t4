# Devlog

## 2026-03-08 (metadata quality and debug observability)

- Added error boundaries in `finalizeRequest`, `processMetadataCapture` so exceptions are recorded as `finalize_error`/`metadata_apply_error` debug events instead of being silently swallowed by the outer `void .catch()`.
- Made `persistTabState` failures inside `appendSessionDebugEvent` non-fatal: storage errors are logged to console but do not block metadata application.
- Added `metadata_attempt` debug event logged immediately before `applyMetadataToSession`, giving a complete trail: `request_completed` → `metadata_attempt` → `metadata_applied`/`metadata_skipped`/`metadata_apply_error`.
- Stopped writing `requestKind: "ignored"` events to the global debug log (still appear in per-session logs). Global log now focused on actionable events.
- Improved episode detection in `metadata_parser.js`: `buildHeuristicCandidate` and `buildCombinedCandidate` now recognise `entityType`/`type` fields with series values (`"show"`, `"series"`, etc.), `numSeasons`/`numberOfEpisodes` count fields, and presence of show-container objects as episode signals even when no explicit `showTitle` key or season/episode numbers are present.
- When entity type signals the payload represents a show/series level (not a specific episode), the main title is used as `showTitle` rather than `episodeTitle`.
- Removed `licensedmanifest` from metadata request classification: it was always parsed by the memberapi parser (which returns null for DRM manifest payloads), producing misleading `metadataParsed: false` events and wasting ~75-160KB of capture buffer per session.
- Added 5 new metadata parser tests covering entity-type detection, series count fields, and show-container title resolution.

## 2026-03-08 (session lifecycle fix)

- Fixed session race condition in `handleTabUpdated`: watch-transition closure now targets sessions by previous watch ID instead of blindly closing the active session. This prevents the pattern where `handleBeforeRequest` creates a session for the new watch ID before `handleTabUpdated` fires, then `handleTabUpdated` immediately closes the new session.
- Fixed bootstrap crash (`Invalid tab ID`) by reconciling stored tab states against real Firefox tabs on startup and making `restoreBadgeState` error-tolerant per tab.
- Added `closeSessionsByWatchId` helper for targeted session closure.
- Added 5 regression tests covering the session-closing logic and the race scenario.

## 2026-03-08

- Added a Firefox-only WebExtension proof of concept under `netflix-firefox-extension/`.
- Implemented passive per-tab capture toggling for Netflix watch pages with runtime host-permission requests, badge state, and persisted tab capture state.
- Added live-response tee handling for Netflix GraphQL metadata, BIF thumbnail files, and TTML subtitle XML files without modifying request or response behavior.
- Added deterministic capture naming under `Netflix Captures/<title-slug>/` plus a manifest JSON file that records parsed title metadata and saved asset paths.
- Added Node-based tests for URL matching, GraphQL metadata parsing, deterministic naming, and extension state storage.
- Hardened GraphQL metadata parsing so empty or non-JSON responses are ignored instead of surfacing runtime errors.
- Moved Netflix/CDN origin declarations to Firefox MV3 `host_permissions` so the browser can actually grant `webRequest` access for those origins.
- Changed the Firefox toggle behavior so capture remains enabled until the user explicitly turns it off, instead of auto-disabling on non-watch navigation.
- Renamed the extension download root from `Netflix Captures` to `Netflix_Captures` and tightened tab-title fallback so plain `Netflix` does not become the content slug.
- Added per-title and global debug JSON logs for every seen candidate request and fixed manifest writing so a title folder no longer accumulates assets from unrelated titles visited in the same tab.
- Moved response filtering earlier for BIF/subtitle/GraphQL request URLs and clear stale metadata when the watch ID changes so episode-to-episode navigation does not inherit the prior title slug.
- Limited GraphQL metadata application to responses whose parsed `videoId` matches the current watch URL and delayed blob URL revocation so Firefox downloads are less likely to fail nondeterministically.
- Replaced the immediate-save background flow with a watch-session aggregator keyed by `watchId`, buffering BIF and subtitle payloads until matching metadata arrives or the watch session closes.
- Added stored-state normalization for older extension state and default-enabled startup behavior for Netflix tabs so background reloads no longer crash or leave tabs inert.
- Fixed a tab-state persistence race in the extension background script so pending BIF/subtitle assets are no longer lost when concurrent request handlers persist state.
- Added Netflix `memberapi/release/metadata` capture and heuristic metadata parsing because GraphQL responses are often empty or unrelated during playback.
- Broadened subtitle XML validation to accept real Netflix timed-text variants that do not always carry the exact `textType="SUBS"` marker.
- Added Netflix `licensedmanifest` as a second metadata source and changed metadata parsing to merge series/season/episode fields across a whole payload so TV episodes stop collapsing into movie-like one-title manifests.
- Added a per-tab series-title hint that carries across direct watch-to-watch transitions, letting next-episode playback reuse the previously resolved show title when the new metadata payload only contains the episode title.
- Updated `README.md` and `ARCHITECTURE.md` to describe the new browser-capture entrypoint and its relationship to the existing local analysis pipeline.
