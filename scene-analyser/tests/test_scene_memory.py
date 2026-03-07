import unittest

from scene_memory import BoundedSceneMemory, summarize_older_subtitles
from subtitle_ingestion import SubtitleEvent


class SceneMemoryTests(unittest.TestCase):
    def test_bounded_scene_memory_uses_recent_scene_windows(self) -> None:
        memory = BoundedSceneMemory(
            [
                SubtitleEvent(1.0, 2.0, "First line."),
                SubtitleEvent(4.2, 5.0, "Second line."),
                SubtitleEvent(8.1, 9.0, "Third line."),
                SubtitleEvent(12.0, 13.0, "Fourth line."),
                SubtitleEvent(16.0, 17.0, "Fifth line."),
            ]
        )
        memory.record_result("scene1.jpg", 0.0, 4.0, {"summary": "Dexter waits."}, None)
        memory.record_result("scene2.jpg", 4.0, 8.0, {"summary": "Deb speaks."}, None)
        memory.record_result("scene3.jpg", 8.0, 12.0, {"summary": "Harry watches."}, None)

        snapshot = memory.build_snapshot(12.0, 16.0)

        self.assertIn("8.0s to 12.0s", snapshot.recent_raw_subtitles)
        self.assertIn("12.0s to 16.0s", snapshot.recent_raw_subtitles)
        self.assertIn("Second line.", snapshot.recent_raw_subtitles)
        self.assertIn("Third line.", snapshot.recent_raw_subtitles)
        self.assertIn("Fourth line.", snapshot.recent_raw_subtitles)
        self.assertIn("First line.", snapshot.older_subtitle_summary)
        self.assertEqual(snapshot.older_event_count, 1)
        self.assertIn("Dexter", snapshot.carry_forward_state["named_entities"])

    def test_summarize_older_subtitles_handles_empty_context(self) -> None:
        self.assertEqual(summarize_older_subtitles([]), "(No earlier subtitle context.)")


if __name__ == "__main__":
    unittest.main()
