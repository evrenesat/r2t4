import unittest

from tdt_format import TDT_FORMAT_ID, TDT_FORMAT_VERSION, validate_tdt


class TdtFormatTests(unittest.TestCase):
    def test_validate_tdt_accepts_minimal_valid_payload(self) -> None:
        payload = {
            "format": TDT_FORMAT_ID,
            "format_version": TDT_FORMAT_VERSION,
            "title_name": "Dexter: Original Sin",
            "source": {"kind": "inference_run"},
            "inputs": {"grid_run_dir": "/tmp/grid"},
            "generation": {"model": "big-model"},
            "research_context": {"enabled": False},
            "subtitle_events": [{"start": 0.5, "end": 1.0, "text": "Hello there"}],
            "segments": [
                {
                    "segment_id": "segment-1",
                    "grid_filename": "scene1.jpg",
                    "start": 0.0,
                    "end": 4.0,
                    "visual_summary": "A person walks into a room.",
                    "dialogue_summary": "A greeting is exchanged.",
                    "combined_narrative": "A person enters and says hello.",
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
        }

        self.assertEqual(validate_tdt(payload), [])

    def test_validate_tdt_rejects_invalid_labels(self) -> None:
        payload = {
            "format": TDT_FORMAT_ID,
            "format_version": TDT_FORMAT_VERSION,
            "title_name": "Title",
            "source": {},
            "inputs": {},
            "generation": {},
            "research_context": {},
            "subtitle_events": [],
            "segments": [
                {
                    "segment_id": "segment-1",
                    "grid_filename": "scene1.jpg",
                    "start": 0.0,
                    "end": 4.0,
                    "visual_summary": "A scene.",
                    "dialogue_summary": "Dialogue.",
                    "combined_narrative": "Combined.",
                    "labels": {
                        "primary_mood": "Panicked",
                        "tension_trend": "Flat",
                        "threat_anticipation": "None",
                        "social_discomfort": "None",
                        "content_warnings": [],
                        "setting": "Indoors",
                    },
                    "carry_forward_state": {},
                    "subtitle_event_indexes": [],
                    "analysis_provenance": {},
                }
            ],
        }

        errors = validate_tdt(payload)

        self.assertIn("segments[0].labels.primary_mood is invalid.", errors)


if __name__ == "__main__":
    unittest.main()
