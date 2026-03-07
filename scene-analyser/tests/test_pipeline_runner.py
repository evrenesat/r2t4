import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline_runner import parse_args, run_pipeline


class PipelineRunnerTests(unittest.TestCase):
    def test_parse_args_defaults(self) -> None:
        with patch("sys.argv", ["pipeline_runner.py"]):
            args = parse_args()
            self.assertEqual(args.config, "config/pipeline.toml")
            self.assertEqual(args.profile, "default")
            self.assertIsNone(args.video_path)

    @patch("pipeline_runner.subprocess.Popen")
    @patch("pipeline_runner.run_inference")
    def test_run_pipeline_orchestrates_extraction_and_inference(
        self,
        mock_run_inference: MagicMock,
        mock_popen: MagicMock,
    ) -> None:
        Path("temp").mkdir(exist_ok=True)
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "Writing run outputs to /tmp/fake_run\n",
            "Grid writing completed.\n",
            "",
        ]
        mock_proc.poll.side_effect = [None, None, 0]
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        mock_run_inference.return_value = Path("/tmp/fake_run/inference_runs/test")

        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            config_path = Path(temp_dir) / "pipeline.toml"
            config_path.write_text(
                """
                [api.fake_api]
                url = "http://fake"

                [models.scene]
                id = "scene-model"
                api = "fake_api"
                context_size = 1000

                [models.summary]
                id = "summary-model"
                api = "fake_api"
                context_size = 1000

                [models.artifact]
                id = "artifact-model"
                api = "fake_api"
                context_size = 1000

                [roles]
                scene_analysis_model = "scene"
                subtitle_summary_model = "summary"
                artifact_model = "artifact"

                [extractor]
                video_path = "/tmp/from-config.mkv"

                [scene_inference]
                strategy = "image_with_precomputed_subtitle_context"
                """,
                encoding="utf-8",
            )

            run_dir = asyncio.run(
                run_pipeline(
                    config_path=config_path,
                    profile="default",
                    video_path=None,
                    limit=5,
                    max_chunk_end_seconds=60.0,
                    output_name="test_out",
                )
            )

        self.assertEqual(str(run_dir), "/tmp/fake_run/inference_runs/test")
        mock_popen.assert_called_once()
        extractor_cmd = mock_popen.call_args.args[0]
        self.assertIn("--config", extractor_cmd)
        self.assertIn("--profile", extractor_cmd)
        self.assertIn("--video-path", extractor_cmd)
        self.assertIn("/tmp/from-config.mkv", extractor_cmd)
        run_config = mock_run_inference.call_args[0][0]
        self.assertEqual(run_config.strategy, "image_with_precomputed_subtitle_context")
        self.assertEqual(run_config.profile, "default")
        self.assertEqual(str(run_config.video_path), "/tmp/from-config.mkv")


if __name__ == "__main__":
    unittest.main()
