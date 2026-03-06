import unittest

from subtitle_ingestion import SubtitleAccumulator, parse_ass_subtitles


ASS_SAMPLE = """[Script Info]
Title: Demo

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\i1}Hello\\Nworld
Dialogue: 0,0:00:04.00,0:00:05.50,Default,,0,0,0,,[MUSIC]
Dialogue: 0,0:00:06.00,0:00:08.00,Default,,0,0,0,,(laughs) We should leave now.
"""


class SubtitleIngestionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
