# Devlog

## 2026-03-06

- Added the second-stage local inference runner for completed grid runs.
- Added subtitle ingestion with external-file override and embedded-stream fallback.
- Added two prompt strategies for experiments: image-only and image plus cumulative raw subtitles.
- Added an OpenAI-compatible chat completions client with JSON repair and explicit per-grid failure records.
- Added unit tests for subtitle parsing, prompt context assembly, and inference orchestration.
- Moved shared prompt/request metadata out of per-grid JSONL rows and into run-level metadata.
- Added per-grid inference timings, run-level aggregate timing stats, and an unattended first-ten-minutes batch runner.
