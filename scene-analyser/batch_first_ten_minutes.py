from __future__ import annotations

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
MAX_CHUNK_END_SECONDS = 200.0
BATCH_NAME = "first_3_minutes"
STRATEGIES = ("image_with_raw_subtitles",)
BATCH_SUMMARY_PREFIX = "batch_first_10_minutes"


def build_run_config(strategy: str) -> RunConfig:
    return RunConfig(
        grid_run_dir=GRID_RUN_DIR,
        video_path=VIDEO_PATH,
        strategy=strategy,
        model=DEFAULT_MODEL,
        chat_completions_url=DEFAULT_CHAT_COMPLETIONS_URL,
        subtitle_path=None,
        subtitle_language="eng",
        subtitle_stream_index=None,
        limit=None,
        max_chunk_end_seconds=MAX_CHUNK_END_SECONDS,
        output_name=BATCH_NAME,
    )


def write_batch_summary(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def run_batch() -> Path:
    batch_started_at = datetime.now().isoformat(timespec="seconds")
    batch_start_perf = datetime.now()
    run_summaries = []

    for strategy in STRATEGIES:
        LOGGER.info("Starting %s run for the first 10 minutes.", strategy)
        run_dir = await run_inference(build_run_config(strategy))
        run_summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        run_summary["run_dir"] = str(run_dir)
        run_summaries.append(run_summary)

    batch_finished_at = datetime.now().isoformat(timespec="seconds")
    inference_runs_dir = GRID_RUN_DIR / "inference_runs"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    summary_path = inference_runs_dir / f"{BATCH_SUMMARY_PREFIX}_{timestamp}.json"
    payload = {
        "batch_name": BATCH_NAME,
        "grid_run_dir": str(GRID_RUN_DIR),
        "video_path": str(VIDEO_PATH),
        "max_chunk_end_seconds": MAX_CHUNK_END_SECONDS,
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
    summary_path = asyncio.run(run_batch())
    LOGGER.info("Batch summary written to %s", summary_path)


if __name__ == "__main__":
    main()
