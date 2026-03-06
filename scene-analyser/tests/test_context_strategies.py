import asyncio
import unittest

from context_strategies import (
    GridRecord,
    ImageOnlyStrategy,
    ImageWithRawSubtitlesStrategy,
    StrategyState,
)
from subtitle_ingestion import SubtitleAccumulator, SubtitleEvent


class ContextStrategyTests(unittest.TestCase):
    def test_image_only_strategy_builds_prompt_without_subtitles(self) -> None:
        strategy = ImageOnlyStrategy()
        grid_record = GridRecord("scene1.jpg", "/tmp/scene1.jpg", 0.0, 4.0)

        prompt_context = asyncio.run(
            strategy.build_context(grid_record, StrategyState(), "system prompt")
        )

        self.assertEqual(prompt_context.strategy, "image_only")
        self.assertIn("0.0s to 4.0s", prompt_context.user_text)
        self.assertEqual(prompt_context.subtitle_context["event_count"], 0)
        self.assertEqual(prompt_context.subtitle_context["text_char_count"], 0)

    def test_raw_subtitle_strategy_uses_cumulative_context(self) -> None:
        strategy = ImageWithRawSubtitlesStrategy()
        events = [
            SubtitleEvent(1.0, 2.0, "First line."),
            SubtitleEvent(3.0, 4.0, "Second line."),
        ]
        state = StrategyState(subtitle_accumulator=SubtitleAccumulator(events))
        grid_record = GridRecord("scene2.jpg", "/tmp/scene2.jpg", 0.0, 4.0)

        prompt_context = asyncio.run(
            strategy.build_context(grid_record, state, "system prompt")
        )

        self.assertEqual(prompt_context.strategy, "image_with_raw_subtitles")
        self.assertIn("First line.\nSecond line.", prompt_context.user_text)
        self.assertEqual(prompt_context.subtitle_context["event_count"], 2)
        self.assertEqual(prompt_context.subtitle_context["text_char_count"], 24)


if __name__ == "__main__":
    unittest.main()
