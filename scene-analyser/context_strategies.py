from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scene_memory import BoundedSceneMemory
from subtitle_ingestion import SubtitleAccumulator

GRIDS_DIRNAME = "grids"
BASE_USER_PROMPT_TEMPLATE = (
    "Analyze the provided movie scene grid as a single chronological scene.\n"
    "Scene timing: {chunk_start:.1f}s to {chunk_end:.1f}s."
)
IMAGE_ONLY_PROMPT_LABEL = "image_only_v1"
RAW_SUBTITLE_TEMPLATE = (
    "Analyze the provided movie scene grid as a single chronological scene.\n"
    "Scene timing: {chunk_start:.1f}s to {chunk_end:.1f}s.\n"
    "Subtitles from the start of the title up to this scene end are included below.\n"
    "Use them only as narrative context; prioritize what is visible in the image.\n"
    "Subtitles:\n{subtitles}"
)
RAW_SUBTITLE_PROMPT_LABEL = "image_with_raw_subtitles_v1"
BOUNDED_MEMORY_TEMPLATE = (
    "Analyze the provided movie scene grid as a single chronological scene.\n"
    "Scene timing: {chunk_start:.1f}s to {chunk_end:.1f}s.\n"
    "Use the image as the primary evidence.\n"
    "Use the bounded subtitle memory only as supporting narrative context.\n"
    "Older subtitle summary:\n{older_subtitle_summary}\n\n"
    "Recent exact subtitles from the last three scene windows:\n{recent_raw_subtitles}\n\n"
    "Carry-forward state from prior successful scene analyses:\n{carry_forward_state}"
)
BOUNDED_MEMORY_PROMPT_LABEL = "image_with_bounded_subtitle_memory_v1"
PRECOMPUTED_MEMORY_TEMPLATE = (
    "Analyze the provided movie scene grid as a single chronological scene.\n"
    "Scene timing: {chunk_start:.1f}s to {chunk_end:.1f}s.\n"
    "Use the image as the primary evidence.\n"
    "Use the provided subtitle summary and recent subtitles only as supporting narrative context.\n"
    "Older subtitle summary:\n{older_subtitle_summary}\n\n"
    "Recent exact subtitles from the last three scene windows:\n{recent_raw_subtitles}"
)
PRECOMPUTED_MEMORY_PROMPT_LABEL = "image_with_precomputed_subtitle_context_v1"


@dataclass(frozen=True)
class GridRecord:
    grid_filename: str
    grid_path: str
    chunk_start: float
    chunk_end: float


@dataclass(frozen=True)
class PromptContext:
    strategy: str
    system_prompt: str
    user_prompt_label: str
    user_text: str
    image_path: str
    subtitle_context: dict[str, float | int | None | str]


@dataclass
class StrategyState:
    subtitle_accumulator: SubtitleAccumulator | None = None
    bounded_scene_memory: BoundedSceneMemory | None = None
    precomputed_summaries: dict[str, dict[str, Any]] | None = None
    precomputed_summaries_path: Path | None = None
    precomputed_row_poll_interval_sec: float = 0.2
    precomputed_row_wait_timeout_sec: float = 300.0


class ContextStrategy(Protocol):
    name: str

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext: ...

    def record_result(
        self,
        grid_record: "GridRecord",
        state: StrategyState,
        analysis: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> None: ...


class ImageOnlyStrategy:
    name = "image_only"

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext:
        await asyncio.sleep(0)
        return PromptContext(
            strategy=self.name,
            system_prompt=system_prompt,
            user_prompt_label=IMAGE_ONLY_PROMPT_LABEL,
            user_text=BASE_USER_PROMPT_TEMPLATE.format(
                chunk_start=grid_record.chunk_start,
                chunk_end=grid_record.chunk_end,
            ),
            image_path=grid_record.grid_path,
            subtitle_context={
                "mode": "none",
                "event_count": 0,
                "context_end": grid_record.chunk_end,
                "text_char_count": 0,
            },
        )

    def record_result(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        analysis: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> None:
        del grid_record, state, analysis, error


class ImageWithRawSubtitlesStrategy:
    name = "image_with_raw_subtitles"

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext:
        if state.subtitle_accumulator is None:
            raise ValueError("The raw subtitle strategy requires a subtitle accumulator.")
        await asyncio.sleep(0)
        subtitles, metadata = state.subtitle_accumulator.advance_to(grid_record.chunk_end)
        return PromptContext(
            strategy=self.name,
            system_prompt=system_prompt,
            user_prompt_label=RAW_SUBTITLE_PROMPT_LABEL,
            user_text=RAW_SUBTITLE_TEMPLATE.format(
                chunk_start=grid_record.chunk_start,
                chunk_end=grid_record.chunk_end,
                subtitles=subtitles or "(No subtitles have appeared yet.)",
            ),
            image_path=grid_record.grid_path,
            subtitle_context={
                "mode": "cumulative_raw",
                "event_count": metadata["event_count"],
                "context_end": metadata["context_end"],
                "last_event_end": metadata["last_event_end"],
                "text_char_count": len(subtitles),
            },
        )

    def record_result(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        analysis: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> None:
        del grid_record, state, analysis, error


class ImageWithBoundedSubtitleMemoryStrategy:
    name = "image_with_bounded_subtitle_memory"

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext:
        if state.bounded_scene_memory is None:
            raise ValueError("The bounded subtitle memory strategy requires scene memory.")
        await asyncio.sleep(0)
        snapshot = state.bounded_scene_memory.build_snapshot(
            grid_record.chunk_start,
            grid_record.chunk_end,
        )
        return PromptContext(
            strategy=self.name,
            system_prompt=system_prompt,
            user_prompt_label=BOUNDED_MEMORY_PROMPT_LABEL,
            user_text=BOUNDED_MEMORY_TEMPLATE.format(
                chunk_start=grid_record.chunk_start,
                chunk_end=grid_record.chunk_end,
                older_subtitle_summary=snapshot.older_subtitle_summary,
                recent_raw_subtitles=snapshot.recent_raw_subtitles,
                carry_forward_state=format_carry_forward_state(snapshot.carry_forward_state),
            ),
            image_path=grid_record.grid_path,
            subtitle_context=snapshot.metadata(grid_record.chunk_end),
        )

    def record_result(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        analysis: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> None:
        if state.bounded_scene_memory is None:
            return
        state.bounded_scene_memory.record_result(
            grid_filename=grid_record.grid_filename,
            chunk_start=grid_record.chunk_start,
            chunk_end=grid_record.chunk_end,
            analysis=analysis,
            error=error,
        )


class ImageWithPrecomputedSubtitleContextStrategy:
    name = "image_with_precomputed_subtitle_context"

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext:
        if state.precomputed_summaries is None:
            raise ValueError("The precomputed subtitle context strategy requires precomputed summaries.")
        summary_row = await wait_for_precomputed_summary_row(state, grid_record.grid_filename)
        if not summary_row:
            older_summary = "No precomputed summary available."
            recent_raw = "No recent subtitles available."
            mode = "missing"
        else:
            older_summary = summary_row.get("summary_text", "") or "(No summary available.)"
            recent_raw = summary_row.get("recent_raw_subtitles", "") or "(No recent subtitles.)"
            mode = str(summary_row.get("status", "precomputed"))
            
        return PromptContext(
            strategy=self.name,
            system_prompt=system_prompt,
            user_prompt_label=PRECOMPUTED_MEMORY_PROMPT_LABEL,
            user_text=PRECOMPUTED_MEMORY_TEMPLATE.format(
                chunk_start=grid_record.chunk_start,
                chunk_end=grid_record.chunk_end,
                older_subtitle_summary=older_summary,
                recent_raw_subtitles=recent_raw,
            ),
            image_path=grid_record.grid_path,
            subtitle_context={
                "mode": mode,
                "summary_available": bool(summary_row and summary_row.get("summary_text")),
                "recent_raw_available": bool(summary_row and summary_row.get("recent_raw_subtitles")),
                "summary_cutoff_second": (
                    summary_row.get("summary_cutoff_second") if summary_row else None
                ),
            },
        )

    def record_result(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        analysis: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> None:
        pass


class FuturePriorAnalysisStrategy:
    name = "image_with_prior_analysis"

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext:
        raise NotImplementedError("Prior-grid analysis context is reserved for a later iteration.")


def build_grid_record(grid_run_dir: Path, manifest_row: dict[str, object]) -> GridRecord:
    grid_filename = str(manifest_row["grid_filename"])
    return GridRecord(
        grid_filename=grid_filename,
        grid_path=str(grid_run_dir / GRIDS_DIRNAME / grid_filename),
        chunk_start=float(manifest_row["chunk_start"]),
        chunk_end=float(manifest_row["chunk_end"]),
    )


def get_strategy(name: str) -> ContextStrategy:
    strategies: dict[str, ContextStrategy] = {
        ImageOnlyStrategy.name: ImageOnlyStrategy(),
        ImageWithRawSubtitlesStrategy.name: ImageWithRawSubtitlesStrategy(),
        ImageWithBoundedSubtitleMemoryStrategy.name: ImageWithBoundedSubtitleMemoryStrategy(),
        ImageWithPrecomputedSubtitleContextStrategy.name: ImageWithPrecomputedSubtitleContextStrategy(),
    }
    try:
        return strategies[name]
    except KeyError as error:
        raise ValueError(f"Unknown strategy {name}.") from error


def get_strategy_prompt_defaults(name: str) -> dict[str, str]:
    templates = {
        ImageOnlyStrategy.name: {
            "user_prompt_label": IMAGE_ONLY_PROMPT_LABEL,
            "user_prompt_template": BASE_USER_PROMPT_TEMPLATE,
        },
        ImageWithRawSubtitlesStrategy.name: {
            "user_prompt_label": RAW_SUBTITLE_PROMPT_LABEL,
            "user_prompt_template": RAW_SUBTITLE_TEMPLATE,
        },
        ImageWithBoundedSubtitleMemoryStrategy.name: {
            "user_prompt_label": BOUNDED_MEMORY_PROMPT_LABEL,
            "user_prompt_template": BOUNDED_MEMORY_TEMPLATE,
        },
        ImageWithPrecomputedSubtitleContextStrategy.name: {
            "user_prompt_label": PRECOMPUTED_MEMORY_PROMPT_LABEL,
            "user_prompt_template": PRECOMPUTED_MEMORY_TEMPLATE,
        },
    }
    try:
        return templates[name]
    except KeyError as error:
        raise ValueError(f"Unknown strategy {name}.") from error


def format_carry_forward_state(carry_forward_state: dict[str, Any]) -> str:
    recent_summaries = carry_forward_state.get("recent_scene_summaries", [])
    summary_lines = [
        f"- {entry['start']:.1f}-{entry['end']:.1f}s {entry['summary']}"
        for entry in recent_summaries
        if isinstance(entry, dict) and "summary" in entry
    ]
    active_threads = carry_forward_state.get("active_threads", [])
    label_snapshot = carry_forward_state.get("label_snapshot", {})
    named_entities = ", ".join(carry_forward_state.get("named_entities", [])) or "None"
    warning_text = (
        ", ".join(carry_forward_state.get("persistent_content_warnings", [])) or "None"
    )
    sections = [
        "Recent scene summaries:",
        "\n".join(summary_lines) if summary_lines else "- None",
        "Active threads:",
        "\n".join(f"- {thread}" for thread in active_threads) if active_threads else "- None",
        f"Named entities: {named_entities}",
        f"Persistent content warnings: {warning_text}",
        f"Latest label snapshot: {label_snapshot or 'None'}",
    ]
    return "\n".join(sections)


async def wait_for_precomputed_summary_row(
    state: StrategyState,
    grid_filename: str,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + state.precomputed_row_wait_timeout_sec
    while True:
        summary_row = state.precomputed_summaries.get(grid_filename)
        if summary_row is not None:
            return summary_row
        refresh_precomputed_summaries(state)
        summary_row = state.precomputed_summaries.get(grid_filename)
        if summary_row is not None:
            return summary_row
        if state.precomputed_summaries_path is None or time.monotonic() >= deadline:
            return None
        await asyncio.sleep(state.precomputed_row_poll_interval_sec)


def refresh_precomputed_summaries(state: StrategyState) -> None:
    if state.precomputed_summaries is None or state.precomputed_summaries_path is None:
        return
    if not state.precomputed_summaries_path.exists():
        return
    for line in state.precomputed_summaries_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        state.precomputed_summaries[str(row["grid_filename"])] = row
