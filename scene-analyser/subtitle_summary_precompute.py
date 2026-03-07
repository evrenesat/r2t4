from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai_compatible_client import CompletionSuccess, OpenAICompatibleClient
from pipeline_config import PipelineConfig
from subtitle_ingestion import (
    NORMALIZED_TRANSCRIPT_FILENAME,
    SubtitleEvent,
    format_normalized_subtitle_line,
    subtitle_start_second,
    write_normalized_subtitle_transcript,
)

LOGGER = logging.getLogger(__name__)
SUMMARY_JSON_KEY = "summary"


@dataclass(frozen=True)
class ChunkWindow:
    chunk_index: int
    start: float
    end: float


def get_summary_cutoff(
    chunk_windows: list[ChunkWindow],
    target_index: int,
    recent_window_count: int = 3,
) -> float:
    first_recent_index = max(0, target_index - (recent_window_count - 1))
    return chunk_windows[first_recent_index].start


def build_summary_prompt(
    normalized_transcript: str,
    cutoff_second: int,
) -> tuple[str, str]:
    if not normalized_transcript.strip():
        return "", ""
    system_prompt = (
        "You summarize subtitle history for a scene analyzer. "
        "The transcript format is 'START_SECOND | text'. "
        "Return a JSON object with a single 'summary' key."
    )
    user_text = (
        "Normalized subtitle transcript for the whole title. "
        "Each line uses the format 'START_SECOND | text'.\n"
        "Ignore subtitle disappearance timing; only start seconds matter.\n\n"
        "Transcript:\n"
        f"{normalized_transcript}\n\n"
        f"Summarize only the subtitle content that starts before second {cutoff_second}. "
        "Do not include lines at or after that second. "
        "Keep the summary concise and focused on durable narrative context."
    )
    return system_prompt, user_text


def build_recent_raw_subtitles(
    events: list[SubtitleEvent],
    cutoff: float,
    chunk_end: float,
) -> str:
    recent_events = [
        event for event in events if event.start >= cutoff and event.start <= chunk_end
    ]
    return "\n".join(format_normalized_subtitle_line(event) for event in recent_events)


async def compute_single_summary(
    chunk: ChunkWindow,
    chunk_windows: list[ChunkWindow],
    events: list[SubtitleEvent],
    normalized_transcript: str,
    config: PipelineConfig,
    client: OpenAICompatibleClient,
    model_alias: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    recent_window_count = config.subtitle_summary_config.recent_window_count
    cutoff = get_summary_cutoff(
        chunk_windows,
        chunk_windows.index(chunk),
        recent_window_count=recent_window_count,
    )
    cutoff_second = max(0, int(cutoff))
    older_events_exist = any(subtitle_start_second(event) < cutoff_second for event in events)
    recent_raw_subtitles = build_recent_raw_subtitles(events, cutoff, chunk.end)
    summary_text = ""
    status = "no_context"
    error_metadata = None

    if older_events_exist:
        system_prompt, user_text = build_summary_prompt(normalized_transcript, cutoff_second)
        completion = await client.generate_json(
            model_alias=model_alias,
            system_prompt=system_prompt,
            user_text=user_text,
            config=config,
        )
        if isinstance(completion, CompletionSuccess):
            summary_text = str(completion.parsed_json.get(SUMMARY_JSON_KEY, "")).strip()
            status = "success"
        else:
            status = "error"
            error_metadata = {
                "type": completion.error_type,
                "message": completion.message,
            }

    safe_start = f"{chunk.start:.1f}".replace(".", "_")
    safe_end = f"{chunk.end:.1f}".replace(".", "_")
    grid_filename = f"scene{chunk.chunk_index}_chunk1_{safe_start}s_to_{safe_end}s.jpg"
    return {
        "grid_filename": grid_filename,
        "chunk_start": chunk.start,
        "chunk_end": chunk.end,
        "summary_cutoff_start": cutoff,
        "summary_cutoff_second": cutoff_second,
        "summary_text": summary_text,
        "recent_raw_subtitles": recent_raw_subtitles,
        "normalized_transcript_filename": config.subtitle_summary_config.normalized_transcript_filename,
        "model_alias": model_alias,
        "status": status,
        "timing_metadata": {"duration_sec": time.perf_counter() - started},
        "error_metadata": error_metadata,
    }


def ensure_normalized_transcript(
    events: list[SubtitleEvent],
    run_dir: Path,
    config: PipelineConfig,
) -> tuple[Path, str]:
    subtitles_dir = run_dir / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    filename = config.subtitle_summary_config.normalized_transcript_filename
    if not filename:
        filename = NORMALIZED_TRANSCRIPT_FILENAME
    transcript_path = subtitles_dir / filename
    transcript_text = write_normalized_subtitle_transcript(events, transcript_path)
    return transcript_path, transcript_text


async def precompute_summaries_async(
    events: list[SubtitleEvent],
    chunk_windows: list[ChunkWindow],
    config: PipelineConfig,
    run_dir: Path,
) -> None:
    contexts_dir = run_dir / config.subtitle_summary_config.contexts_dirname
    contexts_dir.mkdir(parents=True, exist_ok=True)
    cache_path = contexts_dir / config.subtitle_summary_config.summary_cache_filename
    cache_path.write_text("", encoding="utf-8")

    model_alias = config.roles.get("subtitle_summary_model")
    if not model_alias:
        LOGGER.warning("No subtitle_summary_model role configured. Skipping precompute.")
        return

    _, normalized_transcript = ensure_normalized_transcript(events, run_dir, config)
    client = OpenAICompatibleClient()
    tasks = [
        asyncio.create_task(
            compute_single_summary(
                chunk=chunk,
                chunk_windows=chunk_windows,
                events=events,
                normalized_transcript=normalized_transcript,
                config=config,
                client=client,
                model_alias=model_alias,
            )
        )
        for chunk in chunk_windows
    ]

    with cache_path.open("a", encoding="utf-8") as handle:
        for completed in asyncio.as_completed(tasks):
            row = await completed
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
            handle.flush()


def precompute_summaries(
    events: list[SubtitleEvent],
    chunk_windows: list[ChunkWindow],
    config: PipelineConfig,
    run_dir: Path,
) -> None:
    asyncio.run(precompute_summaries_async(events, chunk_windows, config, run_dir))
