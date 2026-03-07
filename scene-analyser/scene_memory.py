from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from subtitle_ingestion import SubtitleEvent

DEFAULT_RECENT_SCENE_WINDOW_COUNT = 3
DEFAULT_SUMMARY_LINE_COUNT = 6
DEFAULT_RECENT_SUMMARY_COUNT = 3
DEFAULT_THREAD_COUNT = 5
DEFAULT_ENTITY_COUNT = 6
NAME_TOKEN_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")
IGNORED_NAME_TOKENS = {
    "A",
    "An",
    "And",
    "But",
    "He",
    "Her",
    "His",
    "I",
    "If",
    "In",
    "It",
    "My",
    "No",
    "So",
    "The",
    "They",
    "This",
    "We",
    "You",
}
LABEL_FIELDS = (
    "primary_mood",
    "tension_trend",
    "threat_anticipation",
    "social_discomfort",
    "setting",
)


@dataclass(frozen=True)
class SceneWindow:
    chunk_start: float
    chunk_end: float


@dataclass(frozen=True)
class SceneAnalysisRecord:
    grid_filename: str
    chunk_start: float
    chunk_end: float
    analysis: dict[str, Any] | None
    error: dict[str, Any] | None


@dataclass(frozen=True)
class BoundedMemorySnapshot:
    older_subtitle_summary: str
    recent_raw_subtitles: str
    carry_forward_state: dict[str, Any]
    recent_subtitle_events: list[SubtitleEvent]
    recent_scene_windows: list[SceneWindow]
    older_event_count: int

    def metadata(self, context_end: float) -> dict[str, Any]:
        return {
            "mode": "bounded_memory",
            "context_end": context_end,
            "older_event_count": self.older_event_count,
            "older_summary_line_count": count_non_empty_lines(self.older_subtitle_summary),
            "older_summary_char_count": len(self.older_subtitle_summary),
            "recent_scene_count": len(self.recent_scene_windows),
            "recent_raw_event_count": len(self.recent_subtitle_events),
            "recent_raw_char_count": len(self.recent_raw_subtitles),
            "carry_forward_scene_count": len(
                self.carry_forward_state.get("recent_scene_summaries", [])
            ),
            "carry_forward_entity_count": len(
                self.carry_forward_state.get("named_entities", [])
            ),
            "carry_forward_warning_count": len(
                self.carry_forward_state.get("persistent_content_warnings", [])
            ),
        }


class BoundedSceneMemory:
    def __init__(
        self,
        subtitle_events: list[SubtitleEvent],
        recent_scene_window_count: int = DEFAULT_RECENT_SCENE_WINDOW_COUNT,
    ) -> None:
        self._subtitle_events = sorted(
            subtitle_events,
            key=lambda event: (event.start, event.end, event.text),
        )
        self._recent_scene_window_count = recent_scene_window_count
        self._scene_history: list[SceneWindow] = []
        self._analysis_history: list[SceneAnalysisRecord] = []

    def build_snapshot(self, chunk_start: float, chunk_end: float) -> BoundedMemorySnapshot:
        recent_windows = [*self._scene_history[-(self._recent_scene_window_count - 1):]]
        recent_windows.append(SceneWindow(chunk_start=chunk_start, chunk_end=chunk_end))
        recent_window_start = min(window.chunk_start for window in recent_windows)
        recent_events = [
            event
            for event in self._subtitle_events
            if event.start <= chunk_end and event.end >= recent_window_start
        ]
        older_events = [
            event
            for event in self._subtitle_events
            if event.start < recent_window_start
        ]
        return BoundedMemorySnapshot(
            older_subtitle_summary=summarize_older_subtitles(older_events),
            recent_raw_subtitles=format_recent_raw_subtitles(recent_windows, recent_events),
            carry_forward_state=build_carry_forward_state(self._analysis_history),
            recent_subtitle_events=recent_events,
            recent_scene_windows=recent_windows,
            older_event_count=len(older_events),
        )

    def record_result(
        self,
        grid_filename: str,
        chunk_start: float,
        chunk_end: float,
        analysis: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> None:
        self._scene_history.append(SceneWindow(chunk_start=chunk_start, chunk_end=chunk_end))
        self._analysis_history.append(
            SceneAnalysisRecord(
                grid_filename=grid_filename,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                analysis=analysis,
                error=error,
            )
        )


def summarize_older_subtitles(
    subtitle_events: list[SubtitleEvent],
    max_lines: int = DEFAULT_SUMMARY_LINE_COUNT,
) -> str:
    if not subtitle_events:
        return "(No earlier subtitle context.)"
    lines = [
        f"{event.start:.1f}-{event.end:.1f}s: {event.text}"
        for event in subtitle_events[-max_lines:]
    ]
    prefix = ""
    if len(subtitle_events) > max_lines:
        prefix = (
            f"Earlier subtitle history condensed from {len(subtitle_events)} events. "
            f"Showing the latest {max_lines} older lines.\n"
        )
    return prefix + "\n".join(lines)


def format_recent_raw_subtitles(
    recent_windows: list[SceneWindow],
    subtitle_events: list[SubtitleEvent],
) -> str:
    if not subtitle_events:
        return "(No subtitles overlap the last scene windows.)"
    window_lines = [
        f"- {window.chunk_start:.1f}s to {window.chunk_end:.1f}s"
        for window in recent_windows
    ]
    subtitle_lines = [
        f"{event.start:.1f}-{event.end:.1f}s: {event.text}"
        for event in subtitle_events
    ]
    return (
        "Scene windows covered:\n"
        + "\n".join(window_lines)
        + "\nRecent raw subtitles:\n"
        + "\n".join(subtitle_lines)
    )


def build_carry_forward_state(
    analysis_history: list[SceneAnalysisRecord],
    recent_summary_count: int = DEFAULT_RECENT_SUMMARY_COUNT,
    thread_count: int = DEFAULT_THREAD_COUNT,
    entity_count: int = DEFAULT_ENTITY_COUNT,
) -> dict[str, Any]:
    successful_records = [record for record in analysis_history if isinstance(record.analysis, dict)]
    recent_records = successful_records[-recent_summary_count:]
    recent_scene_summaries = [
        {
            "grid_filename": record.grid_filename,
            "start": record.chunk_start,
            "end": record.chunk_end,
            "summary": str(record.analysis.get("summary", "")),
        }
        for record in recent_records
        if record.analysis and record.analysis.get("summary")
    ]
    persistent_warnings = sorted(
        {
            warning
            for record in successful_records[-thread_count:]
            for warning in normalize_warnings(record.analysis)
        }
    )
    label_snapshot = build_label_snapshot(successful_records)
    active_threads = [
        summary["summary"] for summary in recent_scene_summaries[-thread_count:]
    ]
    named_entities = extract_named_entities(
        [summary["summary"] for summary in recent_scene_summaries],
        entity_count=entity_count,
    )
    return {
        "recent_scene_summaries": recent_scene_summaries,
        "active_threads": active_threads,
        "label_snapshot": label_snapshot,
        "persistent_content_warnings": persistent_warnings,
        "named_entities": named_entities,
    }


def build_label_snapshot(analysis_history: list[SceneAnalysisRecord]) -> dict[str, Any]:
    successful_records = [record for record in analysis_history if isinstance(record.analysis, dict)]
    if not successful_records:
        return {}
    latest_analysis = successful_records[-1].analysis or {}
    snapshot: dict[str, Any] = {
        field: latest_analysis[field]
        for field in LABEL_FIELDS
        if field in latest_analysis
    }
    snapshot["content_warnings"] = normalize_warnings(latest_analysis)
    return snapshot


def extract_named_entities(
    source_texts: list[str],
    entity_count: int = DEFAULT_ENTITY_COUNT,
) -> list[str]:
    counter: Counter[str] = Counter()
    for text in source_texts:
        for match in NAME_TOKEN_PATTERN.findall(text):
            token = match.strip()
            if token in IGNORED_NAME_TOKENS:
                continue
            counter[token] += 1
    return [
        entity
        for entity, _count in counter.most_common(entity_count)
    ]


def normalize_warnings(analysis: dict[str, Any] | None) -> list[str]:
    if not isinstance(analysis, dict):
        return []
    warnings = analysis.get("content_warnings", [])
    if not isinstance(warnings, list):
        return []
    normalized: list[str] = []
    for warning in warnings:
        if isinstance(warning, str):
            parts = [part.strip() for part in warning.split(",") if part.strip()]
            normalized.extend(parts)
    return normalized


def count_non_empty_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())
