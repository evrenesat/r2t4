# Scene Analyser

This project has two local stages:

1. `extractor_v1.py`
   Builds timestamped 2x2 scene grids from a movie or episode. Subtitle extraction, normalized transcript export, and summary precompute happen here.
2. `pipeline_runner.py` / `inference_runner.py`
   Reads one completed grid run and sends sequential OpenAI-compatible vision requests to a local model endpoint, utilizing precomputed capable-model summaries.
3. `artifact_runner.py`
   Reads one completed inference run and asks a stronger model to generate a validated Timed Descriptive Transcript artifact.

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

## Configuration

The pipeline is driven by a single TOML config at `config/pipeline.toml`.
Instead of defining models and API URLs on the CLI, define them as aliases in the TOML file and select a profile.

Roles are configured:
- `subtitle_summary_model`
- `scene_analysis_model`
- `artifact_model`

## Stage 1: Grid Extraction

Each extractor run writes to a fresh subdirectory such as:

`output/run_balanced_2026-03-06_00-41-08/`

That run directory contains:

- `grids/scene*.jpg`
- `subtitles/`
- `contexts/subtitle_summaries.jsonl`
- `manifest.jsonl`
- `diagnostics.json`

The `subtitles/` directory contains every text subtitle stream the extractor could export from the source title, a `catalog.json` file used by the inference stage, and `normalized_transcript.txt` for cache-friendly summary generation.

Run the extractor directly (or rely on `pipeline_runner.py` to start it):

```bash
uv run python extractor_v1.py
```

## Stage 2: Local Vision Inference

The recommended way to run the pipeline is end-to-end via `pipeline_runner.py`, which starts Stage 1 and then starts Stage 2 according to `execution.summary_gate` in the TOML config:

```bash
uv run python pipeline_runner.py \
  --config config/pipeline.toml \
  --profile default \
  --video-path /path/to/movie.mkv
```

Alternatively, run the inference stage standalone on a completed run directory:

Image plus precomputed subtitle context (default):

```bash
uv run python inference_runner.py \
  --grid-run-dir output/run_balanced_2026-03-06_00-41-08 \
  --strategy image_with_precomputed_subtitle_context \
  --config config/pipeline.toml \
  --profile default
```

### Supported v1 strategies

- `image_with_precomputed_subtitle_context` (recommended)
- `image_only`
- `image_with_raw_subtitles`
- `image_with_bounded_subtitle_memory`

The precomputed strategy reads `contexts/subtitle_summaries.jsonl` and uses:

- a capable-model summary of subtitle history before the current raw tail
- raw subtitle lines for the last three scene windows
- the grid image as the primary evidence

## Stage 3: Timed Descriptive Transcript Generation

The final artifact stage is intentionally separate from scene inference. The small scene-analysis model remains an intermediate signal; a stronger model configured by `artifact_model` authors the final file.

Artifact output path:

`<inference_run_dir>/artifact_runs/<timestamp>_timed_descriptive_transcript_<model>/`

Generate a Timed Descriptive Transcript:

```bash
uv run python artifact_runner.py \
  --inference-run-dir output/run_balanced_2026-03-06_00-41-08/inference_runs/<your_run_dir> \
  --config config/pipeline.toml \
  --profile default \
  --title-name "Dexter: Original Sin"
```

With optional `asky` enrichment (requires `research_model` or `artifact_model` configured in TOML, and `asky` installed):

```bash
uv run python artifact_runner.py \
  --inference-run-dir output/run_balanced_2026-03-06_00-41-08/inference_runs/<your_run_dir> \
  --config config/pipeline.toml \
  --profile default \
  --title-name "Dexter: Original Sin" \
  --asky-research-source-mode web_only
```

### Unattended batch for the first 10 minutes

The repo includes `batch_first_ten_minutes.py`. This uses the new `pipeline_runner.py` configuration to run the first 10 minutes efficiently.

## Verification

```bash
uv run python -m py_compile extractor_v1.py frame_selector.py inference_runner.py subtitle_ingestion.py context_strategies.py openai_compatible_client.py scene_memory.py tdt_format.py artifact_runner.py research_context.py pipeline_config.py pipeline_runner.py subtitle_summary_precompute.py
uv run python -m unittest discover -s tests -p 'test_*.py'
```
