# Devlog

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
