from __future__ import annotations

import importlib
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
SUBTITLES_DIRNAME = "subtitles"
SUBTITLE_CATALOG_FILENAME = "catalog.json"


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
    video_path: Path | None = None,
    subtitle_path: Path | None = None,
    grid_run_dir: Path | None = None,
    subtitle_language: str = "eng",
    subtitle_stream_index: int | None = None,
    allow_subliminal_download: bool = False,
) -> tuple[SubtitleSource, list[SubtitleEvent]]:
    if subtitle_path is not None:
        return load_external_subtitles(subtitle_path)
    if grid_run_dir is not None:
        try:
            return load_extracted_subtitles(
                grid_run_dir, subtitle_language, subtitle_stream_index
            )
        except ValueError:
            if video_path is None:
                raise
    if video_path is not None:
        try:
            return load_embedded_subtitles(video_path, subtitle_language, subtitle_stream_index)
        except ValueError:
            if allow_subliminal_download:
                downloaded = download_subtitles_with_subliminal(
                    video_path,
                    grid_run_dir / SUBTITLES_DIRNAME if grid_run_dir is not None else video_path.parent,
                    subtitle_language,
                )
                if downloaded:
                    return load_downloaded_subtitles(downloaded, subtitle_language)
            raise
    raise ValueError(
        "No subtitles available. Provide --subtitle-path or run inference against a grid run "
        "that includes extracted subtitles."
    )


def load_extracted_subtitles(
    grid_run_dir: Path,
    subtitle_language: str,
    subtitle_stream_index: int | None,
) -> tuple[SubtitleSource, list[SubtitleEvent]]:
    entries = discover_extracted_subtitle_entries(grid_run_dir)
    if not entries:
        raise ValueError(f"No extracted subtitle files found in {grid_run_dir}.")
    stream = choose_subtitle_stream(entries, subtitle_language, subtitle_stream_index)
    subtitle_path = Path(str(stream["identifier"]))
    raw_text = subtitle_path.read_text(encoding="utf-8-sig")
    format_name = normalize_format_name(str(stream["format_name"]))
    events = parse_subtitle_text(raw_text, format_name)
    if not events:
        raise ValueError(f"No subtitle events found in extracted subtitle {subtitle_path}.")
    return SubtitleSource(
        kind="extracted",
        format_name=format_name,
        identifier=str(subtitle_path),
        language=stream.get("language"),
        title=stream.get("title"),
        stream_index=int(stream["index"]) if stream.get("index") is not None else None,
    ), events


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


def export_available_subtitles(
    video_path: Path,
    output_dir: Path,
    subtitle_language: str = "eng",
    allow_subliminal_download: bool = False,
) -> list[SubtitleSource]:
    exported_sources = export_embedded_subtitles(video_path, output_dir)
    if exported_sources or not allow_subliminal_download:
        return exported_sources
    return download_subtitles_with_subliminal(video_path, output_dir, subtitle_language)


def export_embedded_subtitles(video_path: Path, output_dir: Path) -> list[SubtitleSource]:
    streams = discover_embedded_subtitle_streams(video_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    exported_sources: list[SubtitleSource] = []
    catalog_entries: list[dict[str, str | int | None]] = []

    for stream in streams:
        try:
            raw_text = extract_embedded_subtitle_text(
                video_path, int(stream["index"]), str(stream["codec_name"])
            )
            format_name = normalize_format_name(str(stream["codec_name"]))
            output_path = output_dir / build_subtitle_filename(stream, format_name)
            output_path.write_text(raw_text, encoding="utf-8")
        except (ValueError, subprocess.CalledProcessError) as error:
            LOGGER.warning(
                "Skipping subtitle stream %s while exporting subtitles: %s",
                stream.get("index"),
                error,
            )
            continue

        source = SubtitleSource(
            kind="extracted",
            format_name=format_name,
            identifier=str(output_path),
            language=stream.get("language"),
            title=stream.get("title"),
            stream_index=int(stream["index"]),
        )
        exported_sources.append(source)
        catalog_entries.append(
            {
                "index": stream["index"],
                "format_name": format_name,
                "identifier": str(output_path),
                "language": stream.get("language"),
                "title": stream.get("title"),
            }
        )

    catalog_path = output_dir / SUBTITLE_CATALOG_FILENAME
    catalog_path.write_text(json.dumps(catalog_entries, indent=2), encoding="utf-8")
    return exported_sources


def download_subtitles_with_subliminal(
    video_path: Path,
    output_dir: Path,
    subtitle_language: str = "eng",
) -> list[SubtitleSource]:
    try:
        subliminal = importlib.import_module("subliminal")
        babelfish = importlib.import_module("babelfish")
    except ImportError as error:
        raise ValueError("subliminal support is not available in this environment.") from error

    output_dir.mkdir(parents=True, exist_ok=True)
    language = build_subliminal_language(babelfish, subtitle_language)
    video = subliminal.scan_video(str(video_path))
    subtitles_by_video = subliminal.download_best_subtitles(
        {video},
        {language},
        only_one=False,
    )
    subtitles = subtitles_by_video.get(video, [])
    if not subtitles:
        return []

    saved_subtitles = subliminal.save_subtitles(
        video,
        subtitles,
        directory=str(output_dir),
        language_type_suffix=True,
    )
    sources: list[SubtitleSource] = []
    for subtitle in saved_subtitles:
        subtitle_path = Path(subtitle.get_path(video))
        source = SubtitleSource(
            kind="downloaded",
            format_name=normalize_format_name(
                subtitle.subtitle_format or subtitle_path.suffix.lstrip(".")
            ),
            identifier=str(subtitle_path),
            language=get_subtitle_language_code(subtitle),
            title=getattr(subtitle, "provider_name", None),
            stream_index=None,
        )
        sources.append(source)

    write_subtitle_catalog(output_dir, sources)
    return sources


def load_downloaded_subtitles(
    sources: list[SubtitleSource], subtitle_language: str
) -> tuple[SubtitleSource, list[SubtitleEvent]]:
    entries = [
        {
            "index": source.stream_index,
            "format_name": source.format_name,
            "identifier": source.identifier,
            "language": source.language,
            "title": source.title,
        }
        for source in sources
    ]
    chosen = choose_subtitle_stream(entries, subtitle_language, None)
    chosen_source = next(
        source for source in sources if source.identifier == chosen["identifier"]
    )
    events = parse_subtitle_text(
        Path(chosen_source.identifier).read_text(encoding="utf-8-sig"),
        chosen_source.format_name,
    )
    if not events:
        raise ValueError(f"No subtitle events found in downloaded subtitle {chosen_source.identifier}.")
    return chosen_source, events


def discover_extracted_subtitle_entries(
    grid_run_dir: Path,
) -> list[dict[str, str | int | None]]:
    subtitles_dir = grid_run_dir / SUBTITLES_DIRNAME
    catalog_path = subtitles_dir / SUBTITLE_CATALOG_FILENAME
    if catalog_path.exists():
        payload = json.loads(catalog_path.read_text(encoding="utf-8") or "[]")
        return [coerce_subtitle_entry(entry) for entry in payload]

    entries: list[dict[str, str | int | None]] = []
    for path in sorted(subtitles_dir.glob("*")):
        if path.suffix.lower() not in SUBTITLE_TEXT_EXTENSIONS:
            continue
        entries.append(
            {
                "index": None,
                "format_name": normalize_format_name(path.suffix.lstrip(".")),
                "identifier": str(path),
                "language": None,
                "title": None,
            }
        )
    return entries


def write_subtitle_catalog(output_dir: Path, sources: list[SubtitleSource]) -> None:
    catalog_path = output_dir / SUBTITLE_CATALOG_FILENAME
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "index": source.stream_index,
                    "format_name": source.format_name,
                    "identifier": source.identifier,
                    "language": source.language,
                    "title": source.title,
                }
                for source in sources
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


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


def coerce_subtitle_entry(
    entry: dict[str, str | int | None],
) -> dict[str, str | int | None]:
    return {
        "index": entry.get("index"),
        "codec_name": entry.get("codec_name"),
        "format_name": entry.get("format_name") or entry.get("codec_name"),
        "identifier": entry.get("identifier"),
        "language": entry.get("language"),
        "title": entry.get("title"),
    }


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


def build_subtitle_filename(
    stream: dict[str, str | int | None], format_name: str
) -> str:
    parts = [f"stream{int(stream['index']):02d}"]
    language = stream.get("language")
    title = stream.get("title")
    if language:
        parts.append(slugify_subtitle_part(str(language)))
    if title:
        parts.append(slugify_subtitle_part(str(title)))
    return f"{'_'.join(parts)}.{format_name}"


def slugify_subtitle_part(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "subtitle"


def build_subliminal_language(babelfish: object, subtitle_language: str) -> object:
    language_class = getattr(babelfish, "Language")
    normalized = subtitle_language.lower()
    if len(normalized) == 2:
        return language_class.fromalpha2(normalized)
    return language_class.fromalpha3b(normalized)


def get_subtitle_language_code(subtitle: object) -> str | None:
    language = getattr(subtitle, "language", None)
    if language is None:
        return None
    alpha3b = getattr(language, "alpha3b", None)
    if alpha3b:
        return str(alpha3b)
    return str(language)


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
