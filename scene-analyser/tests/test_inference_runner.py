import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inference_runner import RunConfig, run_inference
from openai_compatible_client import CompletionFailure, CompletionSuccess, parse_model_json
from subtitle_ingestion import SubtitleEvent, SubtitleSource


class FakeClient:
    def __init__(self, *_args, **_kwargs) -> None:
        self.calls = 0

    async def analyze(self, model, prompt_context):
        self.calls += 1
        if self.calls == 1:
            return CompletionSuccess(
                parsed_json={"summary": "ok"},
                raw_text='{"summary":"ok"}',
                repaired_json=False,
                retry_count=0,
            )
        return CompletionFailure(
            error_type="transport_error",
            message="timeout",
            raw_text=None,
            repaired_json=False,
            retry_count=0,
        )


class InferenceRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        Path("temp").mkdir(exist_ok=True)

    def test_parse_model_json_repairs_invalid_json(self) -> None:
        result = parse_model_json('{"summary":"hello",}')

        self.assertTrue(result["ok"])
        self.assertTrue(result["repaired_json"])
        self.assertEqual(result["parsed_json"]["summary"], "hello")

    def test_run_inference_writes_results_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            root = Path(temp_dir)
            grid_run_dir = root / "grid_run"
            grid_run_dir.mkdir()
            image_path = grid_run_dir / "scene1.jpg"
            image_path.write_bytes(b"fake image")
            image_path_2 = grid_run_dir / "scene2.jpg"
            image_path_2.write_bytes(b"fake image 2")
            manifest = [
                {"grid_filename": "scene1.jpg", "chunk_start": 0.0, "chunk_end": 4.0},
                {"grid_filename": "scene2.jpg", "chunk_start": 4.0, "chunk_end": 8.0},
            ]
            (grid_run_dir / "manifest.jsonl").write_text(
                "\n".join(json.dumps(row) for row in manifest),
                encoding="utf-8",
            )

            config = RunConfig(
                grid_run_dir=grid_run_dir,
                video_path=Path("/tmp/movie.mkv"),
                strategy="image_only",
                model="model-id",
                chat_completions_url="http://localhost:1234/v1/chat/completions",
                subtitle_path=None,
                subtitle_language="eng",
                subtitle_stream_index=None,
                limit=None,
                max_chunk_end_seconds=None,
                output_name="test",
            )

            with patch("inference_runner.OpenAICompatibleClient", FakeClient):
                run_dir = asyncio.run(run_inference(config))

            results_path = run_dir / "results.jsonl"
            run_metadata_path = run_dir / "run.json"
            rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines()]
            metadata = json.loads(run_metadata_path.read_text(encoding="utf-8"))

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["analysis"]["summary"], "ok")
            self.assertEqual(rows[1]["error"]["error_type"], "transport_error")
            self.assertIn("inference_timing", rows[0])
            self.assertNotIn("prompt_trace", rows[0])
            self.assertEqual(metadata["success_count"], 1)
            self.assertEqual(metadata["error_count"], 1)
            self.assertIn("prompt_defaults", metadata)
            self.assertGreaterEqual(metadata["total_inference_duration_sec"], 0.0)

    def test_run_inference_requires_subtitles_for_raw_strategy(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            root = Path(temp_dir)
            grid_run_dir = root / "grid_run"
            grid_run_dir.mkdir()
            image_path = grid_run_dir / "scene1.jpg"
            image_path.write_bytes(b"fake image")
            (grid_run_dir / "manifest.jsonl").write_text(
                json.dumps({"grid_filename": "scene1.jpg", "chunk_start": 0.0, "chunk_end": 4.0}),
                encoding="utf-8",
            )
            config = RunConfig(
                grid_run_dir=grid_run_dir,
                video_path=Path("/tmp/movie.mkv"),
                strategy="image_with_raw_subtitles",
                model="model-id",
                chat_completions_url="http://localhost:1234/v1/chat/completions",
                subtitle_path=None,
                subtitle_language="eng",
                subtitle_stream_index=None,
                limit=None,
                max_chunk_end_seconds=None,
                output_name=None,
            )

            with patch(
                "inference_runner.load_subtitles",
                return_value=(
                    SubtitleSource(
                        kind="embedded",
                        format_name="ass",
                        identifier="/tmp/movie.mkv",
                        language="eng",
                        stream_index=2,
                    ),
                    [SubtitleEvent(0.5, 1.0, "hello")],
                ),
            ), patch("inference_runner.OpenAICompatibleClient", FakeClient):
                run_dir = asyncio.run(run_inference(config))

            rows = [
                json.loads(line)
                for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(rows[0]["subtitle_context"]["event_count"], 1)

    def test_run_inference_filters_by_chunk_end(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            root = Path(temp_dir)
            grid_run_dir = root / "grid_run"
            grid_run_dir.mkdir()
            (grid_run_dir / "scene1.jpg").write_bytes(b"fake image")
            (grid_run_dir / "scene2.jpg").write_bytes(b"fake image")
            (grid_run_dir / "manifest.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"grid_filename": "scene1.jpg", "chunk_start": 0.0, "chunk_end": 4.0}),
                        json.dumps({"grid_filename": "scene2.jpg", "chunk_start": 604.0, "chunk_end": 612.0}),
                    ]
                ),
                encoding="utf-8",
            )
            config = RunConfig(
                grid_run_dir=grid_run_dir,
                video_path=Path("/tmp/movie.mkv"),
                strategy="image_only",
                model="model-id",
                chat_completions_url="http://localhost:1234/v1/chat/completions",
                subtitle_path=None,
                subtitle_language="eng",
                subtitle_stream_index=None,
                limit=None,
                max_chunk_end_seconds=600.0,
                output_name="test",
            )

            with patch("inference_runner.OpenAICompatibleClient", FakeClient):
                run_dir = asyncio.run(run_inference(config))

            rows = [
                json.loads(line)
                for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["grid_filename"], "scene1.jpg")


if __name__ == "__main__":
    unittest.main()
