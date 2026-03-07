# Architecture

## Overview

The project has two sequential local stages:

1. `extractor_v1.py`
   Detects visually meaningful windows, selects four representative frames, exports available text subtitle streams, and writes one grid run directory with `manifest.jsonl`, `diagnostics.json`, timestamped grid images, and extracted subtitles.
2. `inference_runner.py`
   Reads one completed grid run, optionally resolves subtitles, builds prompt context per grid, and sends sequential OpenAI-compatible vision requests to a local model endpoint.
3. `artifact_runner.py`
   Reads one completed inference run, reloads subtitle events and run metadata, optionally fetches title-level research context via `asky`, and asks a stronger model to author a validated Timed Descriptive Transcript artifact.

## Stage 1 Outputs

Each extractor run lives in its own `output/run_<preset>_<timestamp>/` directory.

- `manifest.jsonl`
  Ordered grid metadata used by downstream inference.
- `diagnostics.json`
  Thresholds, timings, and run-level metrics.
- `grids/scene*.jpg`
  Timestamped 2x2 grid images stored under a dedicated subdirectory.
- `subtitles/`
  Extracted text subtitle streams plus `catalog.json` for downstream subtitle resolution. If no embedded subtitles are present and fallback is enabled, this directory may also contain subtitles downloaded via `subliminal`.

The top-level `output/` directory only retains reusable cache files.

## Stage 2 Components

- `subtitle_ingestion.py`
  Resolves subtitle input from either an external subtitle file, extracted run subtitles, an embedded subtitle stream, or an optional `subliminal` download fallback. It normalizes ASS/SRT/VTT text into ordered subtitle events, exports embedded subtitles during extraction, and exposes a cumulative accumulator for prompt context growth.
- `context_strategies.py`
  Converts one grid record and strategy state into prompt context. V1 supports `image_only`, `image_with_raw_subtitles`, and `image_with_bounded_subtitle_memory`, and resolves image files from the extractor run's `grids/` subdirectory.
- `scene_memory.py`
  Holds deterministic bounded subtitle memory helpers. The bounded strategy keeps exact subtitle lines for the last three scene windows, condenses older subtitle history, and carries forward a small structured state from prior successful scene outputs.
- `openai_compatible_client.py`
  Sends chat completions requests to an OpenAI-compatible endpoint. The same JSON-repair and retry behavior now supports both vision requests with inline image payloads and text-only artifact authoring requests.
- `inference_runner.py`
  CLI entrypoint that orchestrates manifest loading, subtitle resolution, sequential requests, and per-run result writing. Subtitle runs prefer the run-local `subtitles/` directory, so the original movie path is optional in normal operation. A `subliminal` fallback can be enabled explicitly when nothing local is available.
- `tdt_format.py`
  Defines the Timed Descriptive Transcript schema constants and validation rules used by the artifact stage.
- `research_context.py`
  Provides optional lazy `asky` integration so title-level research can enrich artifact generation without becoming a required dependency.
- `artifact_runner.py`
  CLI entrypoint for the final artifact-authoring stage. It loads a completed inference run, validates that enough intermediate analysis exists, invokes the stronger model, validates the returned TDT JSON, and retries with concrete validation feedback when needed.

## Inference Run Artifacts

Each inference experiment is written under:

`<grid_run_dir>/inference_runs/<timestamp>_<strategy>_<model>/`

Artifacts:

- `results.jsonl`
  One row per grid with dynamic subtitle context metadata, per-grid inference timing, parsed analysis JSON or explicit error data. The bounded subtitle memory strategy records observability fields such as older-summary size, recent raw subtitle counts, and carry-forward state counts.
- `run.json`
  Run-level metadata: model, endpoint, prompt defaults, subtitle source, counts, and aggregate timing statistics.

## Artifact Run Artifacts

Each Timed Descriptive Transcript generation is written under:

`<inference_run_dir>/artifact_runs/<timestamp>_timed_descriptive_transcript_<model>/`

Artifacts:

- `timed_descriptive_transcript.json`
  Final validated Timed Descriptive Transcript artifact with subtitle events, timeline segments, labels, provenance, and generation metadata.
- `run.json`
  Artifact-stage metadata: source inference run, stronger model, optional research context, attempt history, validation errors, and final status.

There is also a batch launcher for the first ten minutes:

- `batch_first_ten_minutes.py`
  Runs `image_only` and then `image_with_raw_subtitles` sequentially against the same grid run, supports a CLI model override, and writes a batch summary JSON inside `inference_runs/`.

## Testing Approach

The regression surface is protected with small `unittest` modules that focus on:

- subtitle parsing and cumulative accumulation
- bounded subtitle memory and carry-forward state construction
- strategy prompt assembly
- runner orchestration and result writing
- Timed Descriptive Transcript validation
- optional research adapter behavior
- artifact generation retry and validation behavior
- invalid JSON repair behavior
