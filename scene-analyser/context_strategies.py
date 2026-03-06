from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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


class ContextStrategy(Protocol):
    name: str

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext: ...


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


class FutureSubtitleSummaryStrategy:
    name = "image_with_subtitle_summary"

    async def build_context(
        self,
        grid_record: GridRecord,
        state: StrategyState,
        system_prompt: str,
    ) -> PromptContext:
        raise NotImplementedError("Subtitle summary context is reserved for a later iteration.")


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
    }
    try:
        return templates[name]
    except KeyError as error:
        raise ValueError(f"Unknown strategy {name}.") from error
