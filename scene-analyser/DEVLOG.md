# Devlog

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
- Updated `README.md` and `ARCHITECTURE.md` to describe the new browser-capture entrypoint and its relationship to the existing local analysis pipeline.

## 2026-03-06

- Added the second-stage local inference runner for completed grid runs.
- Added subtitle ingestion with external-file override and embedded-stream fallback.
- Added two prompt strategies for experiments: image-only and image plus cumulative raw subtitles.
- Added an OpenAI-compatible chat completions client with JSON repair and explicit per-grid failure records.
- Added unit tests for subtitle parsing, prompt context assembly, and inference orchestration.
- Moved shared prompt/request metadata out of per-grid JSONL rows and into run-level metadata.
- Added per-grid inference timings, run-level aggregate timing stats, and an unattended first-ten-minutes batch runner.
- Moved extractor grid images under a dedicated `grids/` subdirectory and updated inference path resolution to match.
- Added batch CLI overrides so the default local model can be changed without editing code.
- Added subtitle export during extraction so each run now carries its own `subtitles/` directory and catalog next to the grids.
- Changed inference subtitle resolution to prefer run-local extracted subtitles, making the original movie path optional for normal subtitle-based runs.
- Added optional `subliminal` subtitle download fallback for cases where embedded subtitles are missing.
- Added a bounded subtitle memory strategy that keeps exact subtitle lines for the last three scene windows and compresses older subtitle context into a deterministic summary.
- Added deterministic carry-forward state derived from prior successful scene analyses so scene inference can preserve continuity without growing prompts unboundedly.
- Added a separate Timed Descriptive Transcript artifact stage with schema validation, retry-on-validation-failure, and explicit artifact-run metadata.
- Added optional lazy `asky` integration so artifact generation can enrich title-level context without introducing a hard dependency.
- Added unit tests for bounded scene memory, Timed Descriptive Transcript validation, research-context loading, artifact generation retries, and bounded-memory inference state updates.

## 2026-03-07

- Consolidated runtime settings into `config/pipeline.toml` with alias-based provider resolution and profile overrides.
- Removed hardcoded title paths from the new pipeline path so extractor, pipeline runner, and artifact generation all resolve runtime choices from config first.
- Added normalized subtitle transcript export in `START_SECOND | text` format to support cache-friendly capable-model summary prompts.
- Changed subtitle summary precompute to reuse the same whole-transcript prompt body and vary only the cutoff second and target chunk.
- Kept the extractor alive until summary precompute finishes, while letting `pipeline_runner.py` start inference after grid writing when `summary_gate = "start_when_ready"`.
- Fixed artifact generation to use the config-resolved OpenAI-compatible client path instead of stale direct constructor arguments.
- Updated `ARCHITECTURE.md` and `README.md` to describe the normalized transcript flow, summary gating, and Mermaid runtime diagram.
