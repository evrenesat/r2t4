import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from artifact_runner import ArtifactRunConfig, run_artifact_generation
from pipeline_config import PipelineConfig, ResolvedModelConfig
from openai_compatible_client import CompletionSuccess
from subtitle_ingestion import SubtitleEvent, SubtitleSource
from tdt_format import TDT_FILENAME


class FakeArtifactClient:
    def __init__(self, *_args, **_kwargs) -> None:
        self.calls = 0

    async def generate_json(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return CompletionSuccess(
                parsed_json={"format": "tdt"},
                raw_text='{"format":"tdt"}',
                repaired_json=False,
                retry_count=0,
            )
        return CompletionSuccess(
            parsed_json={
                "format": "tdt",
                "format_version": "1.0",
                "title_name": "Dexter: Original Sin",
                "source": {"kind": "inference_run"},
                "inputs": {"grid_run_dir": "/tmp/grid_run"},
                "generation": {"model": "big-model"},
                "research_context": {"enabled": False},
                "subtitle_events": [
                    {"start": 0.5, "end": 1.0, "text": "Hello there"}
                ],
                "segments": [
                    {
                        "segment_id": "segment-1",
                        "grid_filename": "scene1.jpg",
                        "start": 0.0,
                        "end": 4.0,
                        "visual_summary": "A person enters a room.",
                        "dialogue_summary": "A greeting is spoken.",
                        "combined_narrative": "Someone walks in and says hello.",
                        "labels": {
                            "primary_mood": "Neutral",
                            "tension_trend": "Flat",
                            "threat_anticipation": "None",
                            "social_discomfort": "None",
                            "content_warnings": [],
                            "setting": "Indoors",
                        },
                        "carry_forward_state": {"named_entities": ["Dexter"]},
                        "subtitle_event_indexes": [0],
                        "analysis_provenance": {"source_scene_analysis": "scene1.jpg"},
                    }
                ],
            },
            raw_text='{"format":"tdt"}',
            repaired_json=False,
            retry_count=0,
        )


class ArtifactRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        Path("temp").mkdir(exist_ok=True)

    def test_run_artifact_generation_retries_until_validation_passes(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            root = Path(temp_dir)
            inference_run_dir = root / "inference_run"
            inference_run_dir.mkdir()
            (inference_run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "grid_run_dir": str(root / "grid_run"),
                        "video_path": None,
                        "strategy": "image_with_bounded_subtitle_memory",
                        "model": "small-model",
                        "chat_completions_url": "http://localhost:1234/v1/chat/completions",
                        "subtitle_source": {
                            "kind": "external",
                            "format_name": "srt",
                            "identifier": str(root / "grid_run" / "subtitles" / "movie.srt"),
                            "language": "eng",
                            "stream_index": None,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (inference_run_dir / "results.jsonl").write_text(
                json.dumps(
                    {
                        "grid_filename": "scene1.jpg",
                        "chunk_start": 0.0,
                        "chunk_end": 4.0,
                        "analysis": {
                            "summary": "A person walks into a room.",
                            "primary_mood": "Neutral",
                            "tension_trend": "Flat",
                            "threat_anticipation": "None",
                            "social_discomfort": "None",
                            "content_warnings": [],
                            "setting": "Indoors",
                        },
                        "subtitle_context": {"mode": "bounded_memory"},
                        "error": None,
                    }
                ),
                encoding="utf-8",
            )
            config = ArtifactRunConfig(
                inference_run_dir=inference_run_dir,
                config_path=Path("dummy.toml"),
                profile="default",
                title_name="Dexter: Original Sin",
                asky_research_source_mode=None,
                max_validation_retries=2,
                allow_partial_analysis=False,
            )

            mock_pipeline_config = MagicMock(spec=PipelineConfig)
            mock_pipeline_config.roles = {"artifact_model": "big-model"}
            mock_pipeline_config.resolve_model.return_value = ResolvedModelConfig(
                id="big-model",
                api_url="http://localhost:1234/v1/chat/completions",
                api_key="sk-test",
                context_size=32000,
                image_support=False,
                api_name="lmstudio",
            )

            with patch("artifact_runner.OpenAICompatibleClient", FakeArtifactClient), patch(
                "artifact_runner.PipelineConfig", return_value=mock_pipeline_config
            ), patch(
                "artifact_runner.load_subtitles",
                return_value=(
                    SubtitleSource(
                        kind="external",
                        format_name="srt",
                        identifier="/tmp/movie.srt",
                    ),
                    [SubtitleEvent(0.5, 1.0, "Hello there")],
                ),
            ):
                run_dir = asyncio.run(run_artifact_generation(config))

            artifact_path = run_dir / TDT_FILENAME
            metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertTrue(artifact_path.exists())
            self.assertEqual(metadata["status"], "completed")
            self.assertEqual(len(metadata["attempts"]), 2)

    def test_run_artifact_generation_requires_complete_analysis_by_default(self) -> None:
        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            root = Path(temp_dir)
            inference_run_dir = root / "inference_run"
            inference_run_dir.mkdir()
            (inference_run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "grid_run_dir": str(root / "grid_run"),
                        "video_path": None,
                        "strategy": "image_with_bounded_subtitle_memory",
                        "model": "small-model",
                    }
                ),
                encoding="utf-8",
            )
            (inference_run_dir / "results.jsonl").write_text(
                json.dumps(
                    {
                        "grid_filename": "scene1.jpg",
                        "chunk_start": 0.0,
                        "chunk_end": 4.0,
                        "analysis": None,
                        "subtitle_context": {"mode": "bounded_memory"},
                        "error": {"error_type": "http_error", "message": "400 Bad Request"},
                    }
                ),
                encoding="utf-8",
            )
            config = ArtifactRunConfig(
                inference_run_dir=inference_run_dir,
                config_path=Path("dummy.toml"),
                profile="default",
                title_name="Dexter: Original Sin",
                asky_research_source_mode=None,
                max_validation_retries=2,
                allow_partial_analysis=False,
            )

            mock_pipeline_config = MagicMock(spec=PipelineConfig)
            mock_pipeline_config.roles = {"artifact_model": "big-model"}
            mock_pipeline_config.resolve_model.return_value = ResolvedModelConfig(
                id="big-model",
                api_url="http://localhost:1234/v1/chat/completions",
                api_key="sk-test",
                context_size=32000,
                image_support=False,
                api_name="lmstudio",
            )

            with patch("artifact_runner.PipelineConfig", return_value=mock_pipeline_config):
                with self.assertRaises(ValueError):
                    asyncio.run(run_artifact_generation(config))


if __name__ == "__main__":
    unittest.main()
