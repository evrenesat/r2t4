import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from openai_compatible_client import CompletionSuccess
from pipeline_config import PipelineConfig
from subtitle_ingestion import SubtitleEvent
from subtitle_summary_precompute import (
    ChunkWindow,
    build_summary_prompt,
    get_summary_cutoff,
    precompute_summaries,
)


class TestSubtitleSummaryPrecompute(unittest.TestCase):
    def test_get_summary_cutoff(self) -> None:
        chunks = [
            ChunkWindow(1, 0.0, 10.0),
            ChunkWindow(2, 10.0, 20.0),
            ChunkWindow(3, 20.0, 30.0),
            ChunkWindow(4, 30.0, 40.0),
        ]
        self.assertEqual(get_summary_cutoff(chunks, 0), 0.0)
        self.assertEqual(get_summary_cutoff(chunks, 1), 0.0)
        self.assertEqual(get_summary_cutoff(chunks, 2), 0.0)
        self.assertEqual(get_summary_cutoff(chunks, 3), 10.0)

    def test_build_summary_prompt_uses_full_transcript_and_cutoff(self) -> None:
        system_prompt, user_text = build_summary_prompt("1 | Hello\n5 | World", 10)
        self.assertIn("Transcript:\n1 | Hello\n5 | World", user_text)
        self.assertIn("before second 10", user_text)
        self.assertIn("START_SECOND | text", system_prompt)

        empty_system_prompt, empty_user_text = build_summary_prompt("", 5)
        self.assertEqual(empty_system_prompt, "")
        self.assertEqual(empty_user_text, "")

    @patch("subtitle_summary_precompute.OpenAICompatibleClient")
    def test_precompute_summaries_writes_normalized_transcript_and_cache(
        self,
        mock_client_class,
    ) -> None:
        Path("temp").mkdir(exist_ok=True)
        mock_client = mock_client_class.return_value
        mock_client.generate_json = AsyncMock(
            return_value=CompletionSuccess(
                parsed_json={"summary": "A cool summary"},
                raw_text="...",
                repaired_json=False,
                retry_count=0,
            )
        )

        events = [
            SubtitleEvent(1.1, 2.0, "Hello"),
            SubtitleEvent(5.9, 6.0, "World"),
            SubtitleEvent(15.0, 16.0, "Recent"),
            SubtitleEvent(25.0, 26.0, "More"),
        ]
        chunks = [
            ChunkWindow(1, 0.0, 10.0),
            ChunkWindow(2, 10.0, 20.0),
            ChunkWindow(3, 20.0, 30.0),
            ChunkWindow(4, 30.0, 40.0),
        ]
        config = PipelineConfig()
        config.roles["subtitle_summary_model"] = "qwen_summary"

        with tempfile.TemporaryDirectory(dir="temp") as temp_dir:
            run_dir = Path(temp_dir)
            precompute_summaries(events, chunks, config, run_dir)

            transcript_path = run_dir / "subtitles" / "normalized_transcript.txt"
            cache_path = run_dir / "contexts" / "subtitle_summaries.jsonl"
            self.assertTrue(transcript_path.exists())
            self.assertEqual(
                transcript_path.read_text(encoding="utf-8"),
                "1 | Hello\n5 | World\n15 | Recent\n25 | More",
            )
            self.assertTrue(cache_path.exists())

            rows = [
                json.loads(line)
                for line in cache_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            row_map = {row["grid_filename"]: row for row in rows}
            first_row = row_map["scene1_chunk1_0_0s_to_10_0s.jpg"]
            self.assertEqual(first_row["status"], "no_context")
            self.assertEqual(first_row["recent_raw_subtitles"], "1 | Hello\n5 | World")

            fourth_row = row_map["scene4_chunk1_30_0s_to_40_0s.jpg"]
            self.assertEqual(fourth_row["status"], "success")
            self.assertEqual(fourth_row["summary_text"], "A cool summary")
            self.assertEqual(fourth_row["summary_cutoff_second"], 10)

            mock_client.generate_json.assert_awaited()
            first_call = mock_client.generate_json.await_args_list[0].kwargs
            self.assertIn("1 | Hello\n5 | World\n15 | Recent\n25 | More", first_call["user_text"])


if __name__ == "__main__":
    unittest.main()
