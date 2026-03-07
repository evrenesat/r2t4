import unittest

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from subtitle_ingestion import SubtitleAccumulator, parse_ass_subtitles
from subtitle_ingestion import (
    SUBTITLE_CATALOG_FILENAME,
    SUBTITLES_DIRNAME,
    export_available_subtitles,
    export_embedded_subtitles,
    load_subtitles,
    load_extracted_subtitles,
    SubtitleSource,
)


ASS_SAMPLE = """[Script Info]
Title: Demo

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\i1}Hello\\Nworld
Dialogue: 0,0:00:04.00,0:00:05.50,Default,,0,0,0,,[MUSIC]
Dialogue: 0,0:00:06.00,0:00:08.00,Default,,0,0,0,,(laughs) We should leave now.
"""


class SubtitleIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        Path("temp").mkdir(exist_ok=True)

    def test_parse_ass_subtitles_strips_markup_and_cues(self) -> None:
        events = parse_ass_subtitles(ASS_SAMPLE)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].text, "Hello world")
        self.assertEqual(events[1].text, "We should leave now.")
        self.assertAlmostEqual(events[1].start, 6.0)

    def test_accumulator_advances_incrementally(self) -> None:
        events = parse_ass_subtitles(ASS_SAMPLE)
        accumulator = SubtitleAccumulator(events)

        first_text, first_meta = accumulator.advance_to(2.0)
        second_text, second_meta = accumulator.advance_to(7.0)

        self.assertEqual(first_text, "Hello world")
        self.assertEqual(first_meta["event_count"], 1)
        self.assertEqual(second_text, "Hello world\nWe should leave now.")
        self.assertEqual(second_meta["event_count"], 2)

    def test_export_and_reload_extracted_subtitles_prefers_english(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            grid_run_dir = Path(temp_dir)
            subtitles_dir = grid_run_dir / SUBTITLES_DIRNAME
            streams = [
                {"index": 4, "codec_name": "ass", "language": "spa", "title": "Spanish"},
                {"index": 5, "codec_name": "ass", "language": "eng", "title": "English SDH"},
                {"index": 6, "codec_name": "ass", "language": "eng", "title": "English Alt"},
            ]

            def fake_extract(_video_path: Path, stream_index: int, _codec_name: str) -> str:
                return (
                    ASS_SAMPLE
                    if stream_index == 5
                    else ASS_SAMPLE.replace("Hello", f"Hello-{stream_index}")
                )

            with patch(
                "subtitle_ingestion.discover_embedded_subtitle_streams",
                return_value=streams,
            ), patch(
                "subtitle_ingestion.extract_embedded_subtitle_text",
                side_effect=fake_extract,
            ):
                exported = export_embedded_subtitles(Path("/tmp/movie.mkv"), subtitles_dir)

            self.assertEqual(len(exported), 3)
            catalog = json.loads(
                (subtitles_dir / SUBTITLE_CATALOG_FILENAME).read_text(encoding="utf-8")
            )
            self.assertEqual(len(catalog), 3)

            source, events = load_extracted_subtitles(grid_run_dir, "eng", None)
            self.assertEqual(source.language, "eng")
            self.assertEqual(source.stream_index, 5)
            self.assertEqual(events[0].text, "Hello world")

    def test_export_available_subtitles_falls_back_to_subliminal(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            output_dir = Path(temp_dir) / SUBTITLES_DIRNAME
            downloaded = [
                SubtitleSource(
                    kind="downloaded",
                    format_name="srt",
                    identifier=str(output_dir / "movie.en.srt"),
                    language="eng",
                    title="opensubtitles",
                    stream_index=None,
                )
            ]

            with patch(
                "subtitle_ingestion.export_embedded_subtitles",
                return_value=[],
            ), patch(
                "subtitle_ingestion.download_subtitles_with_subliminal",
                return_value=downloaded,
            ) as download_mock:
                exported = export_available_subtitles(
                    Path("/tmp/movie.mkv"),
                    output_dir,
                    subtitle_language="eng",
                    allow_subliminal_download=True,
                )

            self.assertEqual(exported, downloaded)
            download_mock.assert_called_once()

    def test_load_subtitles_uses_subliminal_when_embedded_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            grid_run_dir = Path(temp_dir) / "grid_run"
            subtitles_dir = grid_run_dir / SUBTITLES_DIRNAME
            subtitles_dir.mkdir(parents=True)
            subtitle_path = subtitles_dir / "movie.en.srt"
            subtitle_path.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nHello from download\n",
                encoding="utf-8",
            )
            downloaded = [
                SubtitleSource(
                    kind="downloaded",
                    format_name="srt",
                    identifier=str(subtitle_path),
                    language="eng",
                    title="opensubtitles",
                    stream_index=None,
                )
            ]

            with patch(
                "subtitle_ingestion.load_extracted_subtitles",
                side_effect=ValueError("missing extracted subtitles"),
            ), patch(
                "subtitle_ingestion.load_embedded_subtitles",
                side_effect=ValueError("missing embedded subtitles"),
            ), patch(
                "subtitle_ingestion.download_subtitles_with_subliminal",
                return_value=downloaded,
            ):
                source, events = load_subtitles(
                    video_path=Path("/tmp/movie.mkv"),
                    grid_run_dir=grid_run_dir,
                    subtitle_language="eng",
                    allow_subliminal_download=True,
                )

            self.assertEqual(source.kind, "downloaded")
            self.assertEqual(events[0].text, "Hello from download")


if __name__ == "__main__":
    unittest.main()
