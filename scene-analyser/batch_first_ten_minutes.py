from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from inference_runner import (
    DEFAULT_CHAT_COMPLETIONS_URL,
    DEFAULT_MODEL,
    RunConfig,
    configure_logging,
    run_inference,
)

LOGGER = logging.getLogger(__name__)

GRID_RUN_DIR = Path("output/run_balanced_2026-03-06_00-41-08")
VIDEO_PATH = Path(
    "/Volumes/DEPO/r2d4-test/movies/DexterOriginalSin-S01E03-MiamiVice.mkv"
)
MAX_CHUNK_END_SECONDS = 600.0
BATCH_NAME = "first_10_minutes"
STRATEGIES = ("image_only", "image_with_raw_subtitles")
BATCH_SUMMARY_PREFIX = "batch_first_10_minutes"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run image-only and subtitle inference for the first 10 minutes."
    )
    parser.add_argument("--grid-run-dir", default=str(GRID_RUN_DIR))
    parser.add_argument("--video-path", default=str(VIDEO_PATH))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--chat-completions-url", default=DEFAULT_CHAT_COMPLETIONS_URL
    )
    parser.add_argument("--output-name", default=BATCH_NAME)
    parser.add_argument(
        "--max-chunk-end-seconds", type=float, default=MAX_CHUNK_END_SECONDS
    )
    parser.add_argument(
        "--allow-subliminal-download",
        action="store_true",
        help="Allow network subtitle download when no extracted or embedded subtitles are available.",
    )
    return parser.parse_args()


def build_run_config(
    strategy: str,
    grid_run_dir: Path,
    video_path: Path,
    model: str,
    chat_completions_url: str,
    output_name: str,
    max_chunk_end_seconds: float,
    allow_subliminal_download: bool,
) -> RunConfig:
    return RunConfig(
        grid_run_dir=grid_run_dir,
        video_path=video_path,
        strategy=strategy,
        model=model,
        chat_completions_url=chat_completions_url,
        subtitle_path=None,
        subtitle_language="eng",
        subtitle_stream_index=None,
        allow_subliminal_download=allow_subliminal_download,
        limit=None,
        max_chunk_end_seconds=max_chunk_end_seconds,
        output_name=output_name,
    )


def write_batch_summary(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def run_batch(args: argparse.Namespace) -> Path:
    batch_started_at = datetime.now().isoformat(timespec="seconds")
    batch_start_perf = datetime.now()
    run_summaries = []
    grid_run_dir = Path(args.grid_run_dir)
    video_path = Path(args.video_path)

    for strategy in STRATEGIES:
        LOGGER.info("Starting %s run for the first 10 minutes.", strategy)
        run_dir = await run_inference(
            build_run_config(
                strategy=strategy,
                grid_run_dir=grid_run_dir,
                video_path=video_path,
                model=args.model,
                chat_completions_url=args.chat_completions_url,
                output_name=args.output_name,
                max_chunk_end_seconds=args.max_chunk_end_seconds,
                allow_subliminal_download=args.allow_subliminal_download,
            )
        )
        run_summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        run_summary["run_dir"] = str(run_dir)
        run_summaries.append(run_summary)

    batch_finished_at = datetime.now().isoformat(timespec="seconds")
    inference_runs_dir = grid_run_dir / "inference_runs"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    summary_path = inference_runs_dir / f"{BATCH_SUMMARY_PREFIX}_{timestamp}.json"
    payload = {
        "batch_name": args.output_name,
        "grid_run_dir": str(grid_run_dir),
        "video_path": str(video_path),
        "model": args.model,
        "chat_completions_url": args.chat_completions_url,
        "allow_subliminal_download": args.allow_subliminal_download,
        "max_chunk_end_seconds": args.max_chunk_end_seconds,
        "strategies": list(STRATEGIES),
        "started_at": batch_started_at,
        "finished_at": batch_finished_at,
        "run_count": len(run_summaries),
        "total_batch_duration_sec": (datetime.now() - batch_start_perf).total_seconds(),
        "total_inference_duration_sec": sum(
            summary["total_inference_duration_sec"] for summary in run_summaries
        ),
        "runs": run_summaries,
    }
    write_batch_summary(summary_path, payload)
    return summary_path


def main() -> None:
    configure_logging()
    args = parse_args()
    summary_path = asyncio.run(run_batch(args))
    LOGGER.info("Batch summary written to %s", summary_path)


if __name__ == "__main__":
    main()
