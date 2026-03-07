from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scene_memory import BoundedSceneMemory
from context_strategies import (
    StrategyState,
    build_grid_record,
    get_strategy,
    get_strategy_prompt_defaults,
)
from openai_compatible_client import (
    CompletionFailure,
    CompletionSuccess,
    OpenAICompatibleClient,
)
from subtitle_ingestion import SubtitleAccumulator, SubtitleSource, load_subtitles

LOGGER = logging.getLogger(__name__)

# DEFAULT_MODEL = "qwen3.5-35b-a3b@iq4_xs"
# DEFAULT_MODEL = "qwen3.5-0.8b-mxfp8-mlx"
DEFAULT_MODEL = "qwen3.5-2b"
DEFAULT_CHAT_COMPLETIONS_URL = "http://localhost:1234/v1/chat/completions"
DEFAULT_SUBTITLE_LANGUAGE = "eng"
DEFAULT_PROMPTS_PATH = Path("prompts.md")
INFERENCE_RUNS_DIRNAME = "inference_runs"
RESULTS_FILENAME = "results.jsonl"
RUN_METADATA_FILENAME = "run.json"
DEFAULT_MAX_CHUNK_END_SECONDS: float | None = None


@dataclass(frozen=True)
class RunConfig:
    grid_run_dir: Path
    video_path: Path | None
    strategy: str
    model: str
    chat_completions_url: str
    subtitle_path: Path | None
    subtitle_language: str
    subtitle_stream_index: int | None
    allow_subliminal_download: bool
    limit: int | None
    max_chunk_end_seconds: float | None
    output_name: str | None


def parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(
        description="Run local scene analysis over an extracted grid run."
    )
    parser.add_argument("--grid-run-dir", required=True)
    parser.add_argument("--video-path")
    parser.add_argument(
        "--strategy",
        required=True,
        choices=[
            "image_only",
            "image_with_raw_subtitles",
            "image_with_bounded_subtitle_memory",
        ],
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--chat-completions-url", default=DEFAULT_CHAT_COMPLETIONS_URL)
    parser.add_argument("--subtitle-path")
    parser.add_argument("--subtitle-language", default=DEFAULT_SUBTITLE_LANGUAGE)
    parser.add_argument("--subtitle-stream-index", type=int)
    parser.add_argument(
        "--allow-subliminal-download",
        action="store_true",
        help="Download subtitles with subliminal if no external, extracted, or embedded subtitles are available.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--max-chunk-end-seconds", type=float, default=DEFAULT_MAX_CHUNK_END_SECONDS
    )
    parser.add_argument("--output-name")
    args = parser.parse_args()
    return RunConfig(
        grid_run_dir=Path(args.grid_run_dir),
        video_path=Path(args.video_path) if args.video_path else None,
        strategy=args.strategy,
        model=args.model,
        chat_completions_url=args.chat_completions_url,
        subtitle_path=Path(args.subtitle_path) if args.subtitle_path else None,
        subtitle_language=args.subtitle_language,
        subtitle_stream_index=args.subtitle_stream_index,
        allow_subliminal_download=args.allow_subliminal_download,
        limit=args.limit,
        max_chunk_end_seconds=args.max_chunk_end_seconds,
        output_name=args.output_name,
    )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_grid_manifest(
    grid_run_dir: Path,
    limit: int | None = None,
    max_chunk_end_seconds: float | None = None,
) -> list[dict[str, Any]]:
    manifest_path = grid_run_dir / "manifest.jsonl"
    rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows.sort(key=lambda row: (float(row["chunk_start"]), float(row["chunk_end"])))
    if max_chunk_end_seconds is not None:
        rows = [row for row in rows if float(row["chunk_end"]) <= max_chunk_end_seconds]
    return rows[:limit] if limit is not None else rows


def load_system_prompt(prompts_path: Path = DEFAULT_PROMPTS_PATH) -> tuple[str, str]:
    prompt_text = prompts_path.read_text(encoding="utf-8").strip()
    digest = hashlib.sha1(prompt_text.encode("utf-8")).hexdigest()[:12]
    return prompt_text, f"prompts_md_{digest}"


def create_inference_run_dir(
    grid_run_dir: Path, strategy: str, model: str, output_name: str | None
) -> Path:
    base_dir = grid_run_dir / INFERENCE_RUNS_DIRNAME
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    model_slug = sanitize_slug(model)
    suffix = sanitize_slug(output_name) if output_name else None
    name_parts = [timestamp, strategy, model_slug]
    if suffix:
        name_parts.append(suffix)
    run_dir = base_dir / "_".join(name_parts)
    variant = 2
    while run_dir.exists():
        run_dir = base_dir / f"{'_'.join(name_parts)}_v{variant}"
        variant += 1
    run_dir.mkdir()
    return run_dir


def sanitize_slug(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "run"


def build_strategy_state(
    strategy_name: str,
    subtitle_source: SubtitleSource | None,
    subtitle_events: list[Any] | None,
) -> StrategyState:
    if strategy_name == "image_with_raw_subtitles":
        if subtitle_source is None or subtitle_events is None:
            raise ValueError(
                "The raw subtitle strategy requires subtitles before the run starts."
            )
        return StrategyState(subtitle_accumulator=SubtitleAccumulator(subtitle_events))
    if strategy_name == "image_with_bounded_subtitle_memory":
        if subtitle_source is None or subtitle_events is None:
            raise ValueError(
                "The bounded subtitle memory strategy requires subtitles before the run starts."
            )
        return StrategyState(
            bounded_scene_memory=BoundedSceneMemory(subtitle_events),
        )
    return StrategyState()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def build_run_metadata(
    config: RunConfig,
    subtitle_source: SubtitleSource | None,
    prompt_version: str,
    system_prompt: str,
    strategy_prompt_defaults: dict[str, str],
    started_at: str,
    total_count: int,
    success_count: int,
    error_count: int,
    inference_durations: list[float],
    finished_at: str | None = None,
) -> dict[str, Any]:
    return {
        "grid_run_dir": str(config.grid_run_dir),
        "video_path": str(config.video_path) if config.video_path is not None else None,
        "strategy": config.strategy,
        "model": config.model,
        "chat_completions_url": config.chat_completions_url,
        "selection_window": {
            "limit": config.limit,
            "max_chunk_end_seconds": config.max_chunk_end_seconds,
        },
        "subtitle_source": subtitle_source.to_dict()
        if subtitle_source is not None
        else None,
        "prompt_defaults": {
            "prompt_version": prompt_version,
            "system_prompt": system_prompt,
            **strategy_prompt_defaults,
        },
        "started_at": started_at,
        "finished_at": finished_at,
        "total_count": total_count,
        "processed_count": success_count + error_count,
        "success_count": success_count,
        "error_count": error_count,
        "run_duration_sec": sum(inference_durations),
        "total_inference_duration_sec": sum(inference_durations),
        "average_inference_duration_sec": (
            sum(inference_durations) / len(inference_durations)
            if inference_durations
            else 0.0
        ),
        "max_inference_duration_sec": max(inference_durations)
        if inference_durations
        else 0.0,
        "min_inference_duration_sec": min(inference_durations)
        if inference_durations
        else 0.0,
        "status": "completed" if finished_at is not None else "running",
    }


async def run_inference(config: RunConfig) -> Path:
    manifest_rows = load_grid_manifest(
        config.grid_run_dir,
        config.limit,
        config.max_chunk_end_seconds,
    )
    system_prompt, prompt_version = load_system_prompt()
    strategy_prompt_defaults = get_strategy_prompt_defaults(config.strategy)
    subtitle_source: SubtitleSource | None = None
    subtitle_events = None

    if config.strategy in {
        "image_with_raw_subtitles",
        "image_with_bounded_subtitle_memory",
    }:
        subtitle_source, subtitle_events = load_subtitles(
            video_path=config.video_path,
            subtitle_path=config.subtitle_path,
            grid_run_dir=config.grid_run_dir,
            subtitle_language=config.subtitle_language,
            subtitle_stream_index=config.subtitle_stream_index,
            allow_subliminal_download=config.allow_subliminal_download,
        )

    run_dir = create_inference_run_dir(
        config.grid_run_dir,
        config.strategy,
        config.model,
        config.output_name,
    )
    results_path = run_dir / RESULTS_FILENAME
    strategy = get_strategy(config.strategy)
    strategy_state = build_strategy_state(
        config.strategy, subtitle_source, subtitle_events
    )
    client = OpenAICompatibleClient(config.chat_completions_url)
    success_count = 0
    error_count = 0
    started_at = datetime.now().isoformat(timespec="seconds")
    run_started_perf = time.perf_counter()
    inference_durations: list[float] = []
    run_metadata_path = run_dir / RUN_METADATA_FILENAME
    results_path.touch()
    write_json(
        run_metadata_path,
        build_run_metadata(
            config=config,
            subtitle_source=subtitle_source,
            prompt_version=prompt_version,
            system_prompt=system_prompt,
            strategy_prompt_defaults=strategy_prompt_defaults,
            started_at=started_at,
            total_count=len(manifest_rows),
            success_count=success_count,
            error_count=error_count,
            inference_durations=inference_durations,
        ),
    )

    for row in manifest_rows:
        grid_record = build_grid_record(config.grid_run_dir, row)
        prompt_context = await strategy.build_context(
            grid_record, strategy_state, system_prompt
        )
        inference_started_at = datetime.now().isoformat(timespec="seconds")
        inference_started_perf = time.perf_counter()
        completion = await client.analyze(config.model, prompt_context)
        inference_duration_sec = time.perf_counter() - inference_started_perf
        inference_finished_at = datetime.now().isoformat(timespec="seconds")
        inference_durations.append(inference_duration_sec)
        payload = build_result_payload(
            row,
            prompt_context,
            completion,
            inference_started_at,
            inference_finished_at,
            inference_duration_sec,
        )
        strategy.record_result(
            grid_record=grid_record,
            state=strategy_state,
            analysis=payload["analysis"],
            error=payload["error"],
        )
        append_jsonl(results_path, payload)
        if isinstance(completion, CompletionSuccess):
            success_count += 1
        else:
            error_count += 1
        write_json(
            run_metadata_path,
            build_run_metadata(
                config=config,
                subtitle_source=subtitle_source,
                prompt_version=prompt_version,
                system_prompt=system_prompt,
                strategy_prompt_defaults=strategy_prompt_defaults,
                started_at=started_at,
                total_count=len(manifest_rows),
                success_count=success_count,
                error_count=error_count,
                inference_durations=inference_durations,
            ),
        )
        LOGGER.info(
            "Processed %s with strategy %s", grid_record.grid_filename, config.strategy
        )

    run_metadata = build_run_metadata(
        config=config,
        subtitle_source=subtitle_source,
        prompt_version=prompt_version,
        system_prompt=system_prompt,
        strategy_prompt_defaults=strategy_prompt_defaults,
        started_at=started_at,
        total_count=len(manifest_rows),
        success_count=success_count,
        error_count=error_count,
        inference_durations=inference_durations,
        finished_at=datetime.now().isoformat(timespec="seconds"),
    )
    run_metadata["run_duration_sec"] = time.perf_counter() - run_started_perf
    write_json(run_metadata_path, run_metadata)
    return run_dir


def build_result_payload(
    manifest_row: dict[str, Any],
    prompt_context: Any,
    completion: CompletionSuccess | CompletionFailure,
    inference_started_at: str,
    inference_finished_at: str,
    inference_duration_sec: float,
) -> dict[str, Any]:
    payload = {
        "grid_filename": manifest_row["grid_filename"],
        "chunk_start": manifest_row["chunk_start"],
        "chunk_end": manifest_row["chunk_end"],
        "subtitle_context": prompt_context.subtitle_context,
        "inference_timing": {
            "started_at": inference_started_at,
            "finished_at": inference_finished_at,
            "duration_sec": inference_duration_sec,
        },
    }
    if isinstance(completion, CompletionSuccess):
        payload.update(
            {
                "analysis": completion.parsed_json,
                "raw_model_text": completion.raw_text,
                "repaired_json": completion.repaired_json,
                "retry_count": completion.retry_count,
                "error": None,
            }
        )
    else:
        payload.update(
            {
                "analysis": None,
                "raw_model_text": completion.raw_text,
                "repaired_json": completion.repaired_json,
                "retry_count": completion.retry_count,
                "error": completion.to_dict(),
            }
        )
    return payload


def main() -> None:
    configure_logging()
    config = parse_args()
    run_dir = asyncio.run(run_inference(config))
    LOGGER.info("Inference results written to %s", run_dir)


if __name__ == "__main__":
    main()
