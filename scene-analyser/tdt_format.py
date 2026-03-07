from __future__ import annotations

from typing import Any

TDT_FORMAT_NAME = "Timed Descriptive Transcript"
TDT_FORMAT_ID = "tdt"
TDT_FORMAT_VERSION = "1.0"
TDT_FILENAME = "timed_descriptive_transcript.json"

PRIMARY_MOOD_OPTIONS = {
    "Tense",
    "Romantic",
    "Comedic",
    "Somber",
    "Action",
    "Peaceful",
    "Mysterious",
    "Awkward",
    "Neutral",
}
TENSION_TREND_OPTIONS = {"Escalating", "Peaking", "Resolving", "Flat"}
THREAT_ANTICIPATION_OPTIONS = {"None", "Looming", "Active"}
SOCIAL_DISCOMFORT_OPTIONS = {"None", "Mild", "Severe"}
SETTING_OPTIONS = {"Indoors", "Outdoors", "Vehicle", "Unknown"}
CONTENT_WARNING_OPTIONS = {
    "Violence",
    "Blood/Gore",
    "Sexual Content",
    "Nudity",
    "Substance Abuse",
    "Flashing Lights",
    "Weaponry",
    "Disturbing Imagery",
}
REQUIRED_TOP_LEVEL_FIELDS = (
    "format",
    "format_version",
    "title_name",
    "source",
    "inputs",
    "generation",
    "research_context",
    "subtitle_events",
    "segments",
)
REQUIRED_SEGMENT_FIELDS = (
    "segment_id",
    "grid_filename",
    "start",
    "end",
    "visual_summary",
    "dialogue_summary",
    "combined_narrative",
    "labels",
    "carry_forward_state",
    "subtitle_event_indexes",
    "analysis_provenance",
)


def validate_tdt(
    payload: dict[str, Any],
    expected_segments: list[dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Artifact payload must be a JSON object."]
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in payload:
            errors.append(f"Missing top-level field: {field}")
    if payload.get("format") != TDT_FORMAT_ID:
        errors.append(f"format must be '{TDT_FORMAT_ID}'.")
    if payload.get("format_version") != TDT_FORMAT_VERSION:
        errors.append(f"format_version must be '{TDT_FORMAT_VERSION}'.")
    subtitle_events = payload.get("subtitle_events")
    if not isinstance(subtitle_events, list):
        errors.append("subtitle_events must be a list.")
        subtitle_events = []
    else:
        errors.extend(validate_subtitle_events(subtitle_events))
    segments = payload.get("segments")
    if not isinstance(segments, list):
        errors.append("segments must be a list.")
        return errors
    errors.extend(validate_segments(segments, len(subtitle_events), expected_segments))
    return errors


def validate_subtitle_events(subtitle_events: list[Any]) -> list[str]:
    errors: list[str] = []
    previous_end = -1.0
    for index, event in enumerate(subtitle_events):
        if not isinstance(event, dict):
            errors.append(f"subtitle_events[{index}] must be an object.")
            continue
        start = event.get("start")
        end = event.get("end")
        text = event.get("text")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append(f"subtitle_events[{index}] start/end must be numeric.")
            continue
        if end < start:
            errors.append(f"subtitle_events[{index}] end must be >= start.")
        if start < previous_end:
            errors.append("subtitle_events must be sorted by timestamp.")
        previous_end = max(previous_end, float(end))
        if not isinstance(text, str) or not text.strip():
            errors.append(f"subtitle_events[{index}] text must be a non-empty string.")
    return errors


def validate_segments(
    segments: list[Any],
    subtitle_event_count: int,
    expected_segments: list[dict[str, Any]] | None,
) -> list[str]:
    errors: list[str] = []
    previous_end = -1.0
    seen_ids: set[str] = set()
    if expected_segments is not None and len(expected_segments) != len(segments):
        errors.append("segments length does not match expected input segments.")
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            errors.append(f"segments[{index}] must be an object.")
            continue
        for field in REQUIRED_SEGMENT_FIELDS:
            if field not in segment:
                errors.append(f"segments[{index}] missing required field: {field}")
        segment_id = segment.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            errors.append(f"segments[{index}] segment_id must be a non-empty string.")
        elif segment_id in seen_ids:
            errors.append(f"segments[{index}] duplicate segment_id: {segment_id}")
        else:
            seen_ids.add(segment_id)
        start = segment.get("start")
        end = segment.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append(f"segments[{index}] start/end must be numeric.")
        else:
            if end < start:
                errors.append(f"segments[{index}] end must be >= start.")
            if start < previous_end:
                errors.append("segments must be sorted by timestamp.")
            previous_end = max(previous_end, float(end))
        validate_string_field(segment, index, "grid_filename", errors)
        validate_string_field(segment, index, "visual_summary", errors)
        validate_string_field(segment, index, "dialogue_summary", errors)
        validate_string_field(segment, index, "combined_narrative", errors)
        labels = segment.get("labels")
        if not isinstance(labels, dict):
            errors.append(f"segments[{index}].labels must be an object.")
        else:
            errors.extend(validate_labels(labels, index))
        carry_forward_state = segment.get("carry_forward_state")
        if not isinstance(carry_forward_state, dict):
            errors.append(f"segments[{index}].carry_forward_state must be an object.")
        analysis_provenance = segment.get("analysis_provenance")
        if not isinstance(analysis_provenance, dict):
            errors.append(f"segments[{index}].analysis_provenance must be an object.")
        subtitle_indexes = segment.get("subtitle_event_indexes")
        if not isinstance(subtitle_indexes, list):
            errors.append(f"segments[{index}].subtitle_event_indexes must be a list.")
        else:
            for subtitle_index in subtitle_indexes:
                if not isinstance(subtitle_index, int):
                    errors.append(
                        f"segments[{index}].subtitle_event_indexes values must be integers."
                    )
                    continue
                if subtitle_index < 0 or subtitle_index >= subtitle_event_count:
                    errors.append(
                        f"segments[{index}].subtitle_event_indexes contains out-of-range value {subtitle_index}."
                    )
        if expected_segments is not None and index < len(expected_segments):
            expected = expected_segments[index]
            expected_grid_filename = expected["grid_filename"]
            if segment.get("grid_filename") != expected_grid_filename:
                errors.append(
                    f"segments[{index}] grid_filename must match expected input segment {expected_grid_filename}."
                )
            if segment.get("start") != expected["chunk_start"]:
                errors.append(
                    f"segments[{index}] start must match expected chunk_start {expected['chunk_start']}."
                )
            if segment.get("end") != expected["chunk_end"]:
                errors.append(
                    f"segments[{index}] end must match expected chunk_end {expected['chunk_end']}."
                )
    return errors


def validate_labels(labels: dict[str, Any], index: int) -> list[str]:
    errors: list[str] = []
    if labels.get("primary_mood") not in PRIMARY_MOOD_OPTIONS:
        errors.append(f"segments[{index}].labels.primary_mood is invalid.")
    if labels.get("tension_trend") not in TENSION_TREND_OPTIONS:
        errors.append(f"segments[{index}].labels.tension_trend is invalid.")
    if labels.get("threat_anticipation") not in THREAT_ANTICIPATION_OPTIONS:
        errors.append(f"segments[{index}].labels.threat_anticipation is invalid.")
    if labels.get("social_discomfort") not in SOCIAL_DISCOMFORT_OPTIONS:
        errors.append(f"segments[{index}].labels.social_discomfort is invalid.")
    if labels.get("setting") not in SETTING_OPTIONS:
        errors.append(f"segments[{index}].labels.setting is invalid.")
    warnings = labels.get("content_warnings")
    if not isinstance(warnings, list):
        errors.append(f"segments[{index}].labels.content_warnings must be a list.")
    else:
        for warning in warnings:
            if warning not in CONTENT_WARNING_OPTIONS:
                errors.append(
                    f"segments[{index}].labels.content_warnings contains invalid value {warning!r}."
                )
    return errors


def validate_string_field(
    segment: dict[str, Any],
    index: int,
    field: str,
    errors: list[str],
) -> None:
    value = segment.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"segments[{index}].{field} must be a non-empty string.")
