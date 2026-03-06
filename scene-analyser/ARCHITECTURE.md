# Architecture

## Overview

The project has two sequential local stages:

1. `extractor_v1.py`
   Detects visually meaningful windows, selects four representative frames, and writes one grid run directory with `manifest.jsonl`, `diagnostics.json`, and timestamped grid images.
2. `inference_runner.py`
   Reads one completed grid run, optionally resolves subtitles, builds prompt context per grid, and sends sequential OpenAI-compatible vision requests to a local model endpoint.

## Stage 1 Outputs

Each extractor run lives in its own `output/run_<preset>_<timestamp>/` directory.

- `manifest.jsonl`
  Ordered grid metadata used by downstream inference.
- `diagnostics.json`
  Thresholds, timings, and run-level metrics.
- `scene*.jpg`
  Timestamped 2x2 grid images.

The top-level `output/` directory only retains reusable cache files.

## Stage 2 Components

- `subtitle_ingestion.py`
  Resolves subtitle input from either an external subtitle file or an embedded subtitle stream. It normalizes ASS/SRT/VTT text into ordered subtitle events and exposes a cumulative accumulator for prompt context growth.
- `context_strategies.py`
  Converts one grid record and strategy state into prompt context. V1 supports `image_only` and `image_with_raw_subtitles`.
- `openai_compatible_client.py`
  Sends chat completions requests with inline image payloads to an OpenAI-compatible endpoint and normalizes success or failure responses.
- `inference_runner.py`
  CLI entrypoint that orchestrates manifest loading, subtitle resolution, sequential requests, and per-run result writing.

## Inference Run Artifacts

Each inference experiment is written under:

`<grid_run_dir>/inference_runs/<timestamp>_<strategy>_<model>/`

Artifacts:

- `results.jsonl`
  One row per grid with dynamic subtitle context metadata, per-grid inference timing, parsed analysis JSON or explicit error data.
- `run.json`
  Run-level metadata: model, endpoint, prompt defaults, subtitle source, counts, and aggregate timing statistics.

There is also a batch launcher for the first ten minutes:

- `batch_first_ten_minutes.py`
  Runs `image_only` and then `image_with_raw_subtitles` sequentially against the same grid run and writes a batch summary JSON inside `inference_runs/`.

## Testing Approach

The regression surface is protected with small `unittest` modules that focus on:

- subtitle parsing and cumulative accumulation
- strategy prompt assembly
- runner orchestration and result writing
- invalid JSON repair behavior
