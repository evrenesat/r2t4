# Scene Analyser

This project has two local stages:

1. `extractor_v1.py`
   Builds timestamped 2x2 scene grids from a movie or episode.
2. `inference_runner.py`
   Reads one completed grid run and sends sequential OpenAI-compatible vision requests to a local model endpoint.

## Setup

Use `uv` for dependency management in this repo.

```bash
uv sync
```

Core dependencies:

- `Pillow`
- `json-repair`

Optional acceleration:

- `numpy`

System dependency:

- `ffmpeg`

## Stage 1: Grid Extraction

Each extractor run writes to a fresh subdirectory such as:

`output/run_balanced_2026-03-06_00-41-08/`

That run directory contains:

- `scene*.jpg`
- `manifest.jsonl`
- `diagnostics.json`

The top-level `output/` directory only keeps reusable cache files.

Run the extractor:

```bash
uv run python extractor_v1.py
```

## Stage 2: Local Vision Inference

The second-stage runner reads an existing extractor run and writes inference outputs back inside it:

`<grid_run_dir>/inference_runs/<timestamp>_<strategy>_<model>/`

Artifacts:

- `results.jsonl`
- `run.json`

`run.json` stores the run-level defaults and shared prompt metadata so `results.jsonl` can stay focused on per-grid outputs and timings.

### Supported v1 strategies

- `image_only`
- `image_with_raw_subtitles`

### Subtitle sources

Resolution order:

1. external subtitle file passed with `--subtitle-path`
2. embedded subtitle stream from the source video

Embedded subtitles currently support text subtitle codecs that can be normalized as ASS, SRT, or VTT. The current sample video exposes an embedded English ASS stream.

### Default local endpoint

- Model: `qwen3.5-35b-a3b@iq4_xs`
- Chat completions URL: `http://localhost:1234/v1/chat/completions`

### Run the inference stage

Image only:

```bash
uv run python inference_runner.py \
  --grid-run-dir output/run_balanced_2026-03-06_00-41-08 \
  --video-path /Volumes/DEPO/r2d4-test/movies/DexterOriginalSin-S01E03-MiamiVice.mkv \
  --strategy image_only
```

Image plus raw subtitles:

```bash
uv run python inference_runner.py \
  --grid-run-dir output/run_balanced_2026-03-06_00-41-08 \
  --video-path /Volumes/DEPO/r2d4-test/movies/DexterOriginalSin-S01E03-MiamiVice.mkv \
  --strategy image_with_raw_subtitles
```

Useful flags:

- `--model`
- `--chat-completions-url`
- `--subtitle-path`
- `--subtitle-language`
- `--subtitle-stream-index`
- `--limit`
- `--max-chunk-end-seconds`
- `--output-name`

### Unattended batch for the first 10 minutes

The repo includes [batch_first_ten_minutes.py](/Users/evren/code/r2t4/scene-analyser/batch_first_ten_minutes.py), which runs `image_only` first and then `image_with_raw_subtitles` for grids whose chunk end is at or before `600` seconds.

Start it in the background:

```bash
mkdir -p temp
nohup uv run python batch_first_ten_minutes.py > temp/batch_first_ten_minutes.log 2>&1 &
```

## Verification

```bash
uv run python -m py_compile extractor_v1.py frame_selector.py inference_runner.py subtitle_ingestion.py context_strategies.py openai_compatible_client.py
uv run python -m unittest discover -s tests -p 'test_*.py'
curl -sS http://localhost:1234/v1/models
```

Smoke runs:

```bash
uv run python inference_runner.py \
  --grid-run-dir output/run_balanced_2026-03-06_00-41-08 \
  --video-path /Volumes/DEPO/r2d4-test/movies/DexterOriginalSin-S01E03-MiamiVice.mkv \
  --strategy image_only \
  --limit 2
```

```bash
uv run python inference_runner.py \
  --grid-run-dir output/run_balanced_2026-03-06_00-41-08 \
  --video-path /Volumes/DEPO/r2d4-test/movies/DexterOriginalSin-S01E03-MiamiVice.mkv \
  --strategy image_with_raw_subtitles \
  --limit 2
```
