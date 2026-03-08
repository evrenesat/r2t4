# Architecture

## Overview

extension is intentionally passive: it observes Netflix watch-page traffic, tees matching BIF and subtitle XML responses, and writes them to the user's download directory for later local analysis.

- `netflix-firefox-extension/background.js`: Toolbar toggle, runtime permission request, per-tab capture state, passive response teeing, metadata correlation, and manifest writing.
- The extension groups candidate watch-page metadata responses, BIFs, and subtitle XML files into watch sessions keyed by the current Netflix `watchId`. Assets are buffered first and only written once the session has metadata or closes.
- Watch-transition closure targets sessions by previous watch ID (`closeSessionsByWatchId`) rather than blindly closing the active session. This prevents a race where `handleBeforeRequest` creates a session for the new watch ID before `handleTabUpdated` fires.
- Bootstrap reconciles stored tab states against real Firefox tabs so stale tab IDs from previous sessions do not crash badge restoration.
- Watch naming uses Netflix `memberapi/release/metadata` responses (preferred) and GraphQL when it yields a better exact-match title payload. `licensedmanifest` is no longer captured — its DRM payload is not parseable as title metadata.
- Metadata parsing merges title fields across an entire playback metadata payload. The parser also recognises `entityType`/`type` series markers, `numSeasons`/`numberOfEpisodes` count fields, and nested `show`/`series` container objects as episode signals so TV shows are correctly identified even when no explicit season/episode numbers appear.
- Error boundaries in `finalizeRequest` and `processMetadataCapture` record exceptions as `finalize_error`/`metadata_apply_error` debug events so failures are visible in saved debug JSON rather than only on the browser console. Storage errors during debug event persistence are non-fatal and do not block metadata application.
- The background state also carries a narrow per-tab series-title hint across direct watch-to-watch transitions so autoplay/manual next-episode navigation can reuse the previous show title when the new metadata payload only exposes an episode title.
- The extension writes per-title manifests and per-title/global debug JSON logs so inconsistent CDN behavior can be diagnosed from saved request metadata.
- `netflix-firefox-extension/lib/*.js`: Pure helpers for request matching, metadata parsing, deterministic file naming, and persisted tab state.
- `netflix-firefox-extension/tests/*.test.js`: Node-based regression tests for the pure capture helpers.

The extension does not modify Netflix player APIs, page DOM, request URLs, request headers, or response bytes. Its role is limited to exporting BIF and subtitle assets that can later feed the existing local pipeline. Once the user toggles capture on for a Netflix tab, it stays enabled until the user clicks the toolbar icon again or closes the tab.

The Firefox extension helpers are covered separately with small `node --test` suites for URL matching, metadata parsing, file naming, and storage semantics.
