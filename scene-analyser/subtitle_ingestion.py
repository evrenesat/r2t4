from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

LOGGER = logging.getLogger(__name__)

ASS_DIALOGUE_PREFIX = "Dialogue:"
ASS_DEFAULT_FIELDS = [
    "Layer",
    "Start",
    "End",
    "Style",
    "Name",
    "MarginL",
    "MarginR",
    "MarginV",
    "Effect",
    "Text",
]
SUBTITLE_TEXT_EXTENSIONS = {".ass", ".ssa", ".srt", ".vtt"}
ASS_TAG_PATTERN = re.compile(r"\{[^}]*\}")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
BRACKET_CUE_PATTERN = re.compile(r"\[[^\]]+\]")
PAREN_CUE_PATTERN = re.compile(r"\((?:applause|laughs?|music|sighs?|gasps?|groans?|panting|door opens?|"
                               r"door closes?|phone rings?|crying|grunts?|moans?|whispers?|breathing|"
                               r"chuckles?|screams?|shouting|yells?|sirens?|gunshots?|engine revs?|"
                               r"indistinct chatter|inaudible|speaking [^)]+|singing|alarm[^)]*)\)",
                               re.IGNORECASE)
LEADING_MUSIC_PATTERN = re.compile(r"^[♪♩♫]+\s*")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class SubtitleEvent:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


@dataclass(frozen=True)
class SubtitleSource:
    kind: str
    format_name: str
    identifier: str
    language: str | None = None
    title: str | None = None
    stream_index: int | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return asdict(self)


class SubtitleAccumulator:
    def __init__(self, events: list[SubtitleEvent]) -> None:
        self._events = sorted(events, key=lambda event: (event.start, event.end))
        self._cursor = 0
        self._chunks: list[str] = []
        self._last_event_end: float | None = None

    def advance_to(self, timestamp: float) -> tuple[str, dict[str, float | int | None]]:
        while self._cursor < len(self._events) and self._events[self._cursor].start <= timestamp:
            event = self._events[self._cursor]
            self._chunks.append(event.text)
            self._last_event_end = event.end
            self._cursor += 1

        return "\n".join(self._chunks), {
            "event_count": self._cursor,
            "last_event_end": self._last_event_end,
            "context_end": timestamp,
        }


def load_subtitles(
    video_path: Path,
    subtitle_path: Path | None = None,
    subtitle_language: str = "eng",
    subtitle_stream_index: int | None = None,
) -> tuple[SubtitleSource, list[SubtitleEvent]]:
    if subtitle_path is not None:
        return load_external_subtitles(subtitle_path)
    return load_embedded_subtitles(video_path, subtitle_language, subtitle_stream_index)


def load_external_subtitles(path: Path) -> tuple[SubtitleSource, list[SubtitleEvent]]:
    if path.suffix.lower() not in SUBTITLE_TEXT_EXTENSIONS:
        raise ValueError(f"Unsupported subtitle extension for {path}.")
    raw_text = path.read_text(encoding="utf-8-sig")
    format_name = normalize_format_name(path.suffix.lower().lstrip("."))
    events = parse_subtitle_text(raw_text, format_name)
    if not events:
        raise ValueError(f"No subtitle events found in {path}.")
    return SubtitleSource(
        kind="external",
        format_name=format_name,
        identifier=str(path),
    ), events


def load_embedded_subtitles(
    video_path: Path,
    subtitle_language: str,
    subtitle_stream_index: int | None,
) -> tuple[SubtitleSource, list[SubtitleEvent]]:
    streams = discover_embedded_subtitle_streams(video_path)
    if not streams:
        raise ValueError(f"No embedded subtitle streams found in {video_path}.")
    stream = choose_subtitle_stream(streams, subtitle_language, subtitle_stream_index)
    raw_text = extract_embedded_subtitle_text(video_path, stream["index"], stream["codec_name"])
    format_name = normalize_format_name(stream["codec_name"])
    events = parse_subtitle_text(raw_text, format_name)
    if not events:
        raise ValueError(f"No subtitle events parsed from embedded stream {stream['index']}.")
    return SubtitleSource(
        kind="embedded",
        format_name=format_name,
        identifier=str(video_path),
        language=stream.get("language"),
        title=stream.get("title"),
        stream_index=stream["index"],
    ), events


def discover_embedded_subtitle_streams(video_path: Path) -> list[dict[str, str | int | None]]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=index,codec_name:stream_tags=language,title",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout or "{}")
    streams = []
    for stream in payload.get("streams", []):
        tags = stream.get("tags", {})
        streams.append(
            {
                "index": stream["index"],
                "codec_name": stream.get("codec_name", "unknown"),
                "language": tags.get("language"),
                "title": tags.get("title"),
            }
        )
    return streams


def choose_subtitle_stream(
    streams: list[dict[str, str | int | None]],
    subtitle_language: str,
    subtitle_stream_index: int | None,
) -> dict[str, str | int | None]:
    if subtitle_stream_index is not None:
        for stream in streams:
            if stream["index"] == subtitle_stream_index:
                return stream
        raise ValueError(f"Subtitle stream index {subtitle_stream_index} was not found.")

    for stream in streams:
        if stream.get("language") == subtitle_language:
            return stream
    return streams[0]


def extract_embedded_subtitle_text(video_path: Path, stream_index: int, codec_name: str) -> str:
    output_format = subtitle_ffmpeg_format(codec_name)
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(video_path),
        "-map",
        f"0:{stream_index}",
        "-f",
        output_format,
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        raise ValueError(f"Embedded subtitle stream {stream_index} produced no text.")
    return result.stdout


def subtitle_ffmpeg_format(codec_name: str) -> str:
    normalized = normalize_format_name(codec_name)
    if normalized == "ass":
        return "ass"
    if normalized == "srt":
        return "srt"
    if normalized == "vtt":
        return "webvtt"
    raise ValueError(f"Unsupported embedded subtitle codec {codec_name}.")


def normalize_format_name(name: str) -> str:
    lowered = name.lower()
    if lowered in {"ssa", "ass"}:
        return "ass"
    if lowered in {"srt", "subrip"}:
        return "srt"
    if lowered in {"webvtt", "vtt"}:
        return "vtt"
    return lowered


def parse_subtitle_text(raw_text: str, format_name: str) -> list[SubtitleEvent]:
    normalized = normalize_format_name(format_name)
    if normalized == "ass":
        return parse_ass_subtitles(raw_text)
    if normalized == "srt":
        return parse_srt_subtitles(raw_text)
    if normalized == "vtt":
        return parse_vtt_subtitles(raw_text)
    raise ValueError(f"Unsupported subtitle format {format_name}.")


def parse_ass_subtitles(raw_text: str) -> list[SubtitleEvent]:
    fields = ASS_DEFAULT_FIELDS
    events: list[SubtitleEvent] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Format:"):
            fields = [field.strip() for field in stripped.split(":", 1)[1].split(",")]
            continue
        if not stripped.startswith(ASS_DIALOGUE_PREFIX):
            continue
        payload = stripped[len(ASS_DIALOGUE_PREFIX):].lstrip()
        parts = payload.split(",", len(fields) - 1)
        if len(parts) != len(fields):
            LOGGER.debug("Skipping malformed ASS dialogue line: %s", stripped)
            continue
        record = dict(zip(fields, parts, strict=False))
        text = normalize_subtitle_text(record.get("Text", ""))
        if not text:
            continue
        events.append(
            SubtitleEvent(
                start=parse_ass_timestamp(record["Start"]),
                end=parse_ass_timestamp(record["End"]),
                text=text,
            )
        )
    return events


def parse_srt_subtitles(raw_text: str) -> list[SubtitleEvent]:
    events: list[SubtitleEvent] = []
    for block in split_subtitle_blocks(raw_text):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing_index = 1 if len(lines) >= 2 and "-->" in lines[1] else 0
        if timing_index >= len(lines) or "-->" not in lines[timing_index]:
            continue
        start_text, end_text = [part.strip() for part in lines[timing_index].split("-->", 1)]
        content = normalize_subtitle_text(" ".join(lines[timing_index + 1:]))
        if not content:
            continue
        events.append(
            SubtitleEvent(
                start=parse_srt_timestamp(start_text),
                end=parse_srt_timestamp(end_text),
                text=content,
            )
        )
    return events


def parse_vtt_subtitles(raw_text: str) -> list[SubtitleEvent]:
    events: list[SubtitleEvent] = []
    for block in split_subtitle_blocks(raw_text.replace("WEBVTT", "", 1)):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing_index = 1 if len(lines) >= 2 and "-->" in lines[1] else 0
        if timing_index >= len(lines) or "-->" not in lines[timing_index]:
            continue
        start_text, end_text = [part.strip() for part in lines[timing_index].split("-->", 1)]
        content = normalize_subtitle_text(" ".join(lines[timing_index + 1:]))
        if not content:
            continue
        events.append(
            SubtitleEvent(
                start=parse_vtt_timestamp(start_text),
                end=parse_vtt_timestamp(end_text),
                text=content,
            )
        )
    return events


def split_subtitle_blocks(raw_text: str) -> Iterable[str]:
    return re.split(r"\n\s*\n", raw_text.strip())


def normalize_subtitle_text(raw_text: str) -> str:
    text = raw_text.replace("\\N", " ").replace("\\n", " ")
    text = ASS_TAG_PATTERN.sub("", text)
    text = HTML_TAG_PATTERN.sub("", text)
    text = BRACKET_CUE_PATTERN.sub(" ", text)
    text = PAREN_CUE_PATTERN.sub(" ", text)
    text = LEADING_MUSIC_PATTERN.sub("", text)
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    return text


def parse_ass_timestamp(value: str) -> float:
    hours_text, minutes_text, seconds_text = value.strip().split(":")
    seconds, centiseconds = seconds_text.split(".")
    return (
        int(hours_text) * 3600
        + int(minutes_text) * 60
        + int(seconds)
        + int(centiseconds) / 100
    )


def parse_srt_timestamp(value: str) -> float:
    hours_text, minutes_text, seconds_text = value.strip().split(":")
    seconds, milliseconds = seconds_text.split(",")
    return (
        int(hours_text) * 3600
        + int(minutes_text) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


def parse_vtt_timestamp(value: str) -> float:
    hours_text, minutes_text, seconds_text = value.strip().split(":")
    seconds, milliseconds = seconds_text.split(".")
    return (
        int(hours_text) * 3600
        + int(minutes_text) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )
