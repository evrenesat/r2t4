import os
import tempfile
import unittest
from pathlib import Path

from pipeline_config import ConfigError, PipelineConfig


class TestPipelineConfig(unittest.TestCase):
    def setUp(self) -> None:
        Path("temp").mkdir(exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir="temp")
        self.config_path = Path(self.temp_dir.name) / "pipeline.toml"
        self.config_path.write_text(
            """
            [api.test_api]
            url = "http://test/v1"
            api_key_env = "TEST_API_KEY"

            [api.bad_api]
            url = "https://anthropic.com/v1"

            [models.test_model]
            id = "test-model-id"
            api = "test_api"
            context_size = 8000

            [models.bad_model]
            id = "bad-model-id"
            api = "bad_api"
            context_size = 8000

            [roles]
            artifact_model = "test_model"

            [execution]
            summary_gate = "start_when_ready"

            [extractor]
            video_path = "/tmp/from-config.mkv"

            [scene_inference]
            strategy = "image_with_precomputed_subtitle_context"

            [profiles.remote.roles]
            artifact_model = "bad_model"
            """,
            encoding="utf-8",
        )
        os.environ["TEST_API_KEY"] = "secret123"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("TEST_API_KEY", None)

    def test_load_config(self) -> None:
        config = PipelineConfig(self.config_path)
        self.assertIn("test_api", config.apis)
        self.assertIn("test_model", config.models)
        self.assertEqual(config.execution_config.summary_gate, "start_when_ready")
        self.assertEqual(
            config.scene_inference_config.strategy,
            "image_with_precomputed_subtitle_context",
        )

    def test_resolve_model_defaults_image_support_true(self) -> None:
        config = PipelineConfig(self.config_path)
        resolved = config.resolve_model("test_model")
        self.assertEqual(resolved.id, "test-model-id")
        self.assertEqual(resolved.api_url, "http://test/v1")
        self.assertEqual(resolved.api_key, "secret123")
        self.assertTrue(resolved.image_support)

    def test_get_role_model(self) -> None:
        config = PipelineConfig(self.config_path)
        resolved = config.get_role_model("artifact_model")
        self.assertEqual(resolved.id, "test-model-id")

    def test_missing_model(self) -> None:
        config = PipelineConfig(self.config_path)
        with self.assertRaises(ConfigError):
            config.resolve_model("nonexistent")

    def test_resolve_video_path_prefers_override(self) -> None:
        config = PipelineConfig(self.config_path)
        self.assertEqual(str(config.resolve_video_path(Path("/tmp/override.mkv"))), "/tmp/override.mkv")
        self.assertEqual(str(config.resolve_video_path()), "/tmp/from-config.mkv")


if __name__ == "__main__":
    unittest.main()
