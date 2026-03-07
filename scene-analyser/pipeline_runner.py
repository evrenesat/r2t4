from __future__ import annotations

import argparse
import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from inference_runner import RunConfig, run_inference
from pipeline_config import PipelineConfig

LOGGER = logging.getLogger(__name__)
EXTRACTOR_READY_LINE = "Grid writing completed."
SUMMARY_READY_LINE = "Summary precomputation finished."
RUN_OUTPUT_PREFIX = "Writing run outputs to "


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the end-to-end pipeline.")
    parser.add_argument("--config", default="config/pipeline.toml")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--video-path")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-chunk-end-seconds", type=float)
    parser.add_argument("--output-name")
    return parser.parse_args()


def _extract_run_dir_from_line(line: str) -> Path | None:
    if RUN_OUTPUT_PREFIX not in line:
        return None
    return Path(line.split(RUN_OUTPUT_PREFIX, maxsplit=1)[1].strip())


def _drain_stdout(stdout: TextIO | None) -> None:
    if stdout is None:
        return
    for line in stdout:
        print(f"[Extractor] {line}", end="")


async def wait_for_extractor_ready(
    proc: subprocess.Popen[str],
    summary_gate: str,
) -> Path:
    if proc.stdout is None:
        raise RuntimeError("Extractor process did not expose stdout.")
    ready_line = SUMMARY_READY_LINE if summary_gate == "wait_for_all_summaries" else EXTRACTOR_READY_LINE
    run_dir: Path | None = None

    while True:
        line = await asyncio.to_thread(proc.stdout.readline)
        if not line:
            if proc.poll() is not None:
                break
            await asyncio.sleep(0.1)
            continue
        print(f"[Extractor] {line}", end="")
        maybe_run_dir = _extract_run_dir_from_line(line)
        if maybe_run_dir is not None:
            run_dir = maybe_run_dir
        if ready_line in line:
            break

    if run_dir is None:
        return_code = proc.wait()
        raise RuntimeError(f"Extractor failed before reporting a run directory (exit {return_code}).")

    asyncio.create_task(asyncio.to_thread(_drain_stdout, proc.stdout))
    return run_dir


async def run_pipeline(
    config_path: Path,
    profile: str,
    video_path: Path | None = None,
    limit: int | None = None,
    max_chunk_end_seconds: float | None = None,
    output_name: str | None = None,
) -> Path:
    pipeline_config = PipelineConfig(config_path, profile)
    resolved_video_path = pipeline_config.resolve_video_path(video_path)
    summary_gate = pipeline_config.execution_config.summary_gate
    strategy = pipeline_config.scene_inference_config.strategy

    extractor_cmd = [
        sys.executable,
        "extractor_v1.py",
        "--config",
        str(config_path),
        "--profile",
        profile,
        "--video-path",
        str(resolved_video_path),
    ]
    LOGGER.info("Starting stage 1 extraction with %s", extractor_cmd)
    proc = subprocess.Popen(
        extractor_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    grid_run_dir = await wait_for_extractor_ready(proc, summary_gate)

    run_config = RunConfig(
        grid_run_dir=grid_run_dir,
        video_path=resolved_video_path,
        strategy=strategy,
        config_path=config_path,
        profile=profile,
        subtitle_path=None,
        subtitle_language=pipeline_config.subtitle_ingestion_config.subtitle_language,
        subtitle_stream_index=pipeline_config.subtitle_ingestion_config.subtitle_stream_index,
        allow_subliminal_download=pipeline_config.subtitle_ingestion_config.allow_subliminal_download,
        limit=limit,
        max_chunk_end_seconds=max_chunk_end_seconds,
        output_name=output_name,
    )

    LOGGER.info("Starting scene inference with strategy %s", strategy)
    inference_run_dir = await run_inference(run_config)
    extractor_return_code = proc.wait()
    if extractor_return_code != 0:
        raise RuntimeError(f"Extractor exited with status {extractor_return_code}.")
    return inference_run_dir


def main() -> None:
    configure_logging()
    args = parse_args()
    try:
        run_dir = asyncio.run(
            run_pipeline(
                config_path=Path(args.config),
                profile=args.profile,
                video_path=Path(args.video_path) if args.video_path else None,
                limit=args.limit,
                max_chunk_end_seconds=args.max_chunk_end_seconds,
                output_name=args.output_name,
            )
        )
        LOGGER.info("Pipeline completed successfully. Output in %s", run_dir)
    except KeyboardInterrupt:
        LOGGER.info("Pipeline interrupted by user.")


if __name__ == "__main__":
    main()
