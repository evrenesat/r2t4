import types
import unittest
from unittest.mock import patch

from research_context import load_research_context


class ResearchContextTests(unittest.TestCase):
    def test_load_research_context_returns_disabled_without_alias(self) -> None:
        result = load_research_context("Dexter: Original Sin", None)

        self.assertFalse(result.enabled)
        self.assertIn("not requested", result.notices[0])

    def test_load_research_context_handles_missing_asky(self) -> None:
        with patch("research_context.importlib.import_module", side_effect=ImportError):
            result = load_research_context("Dexter: Original Sin", "gf")

        self.assertFalse(result.enabled)
        self.assertEqual(result.provider, "asky")

    def test_load_research_context_uses_asky_when_available(self) -> None:
        class FakeAskyClient:
            def __init__(self, _config) -> None:
                pass

            def run_turn(self, _request):
                return types.SimpleNamespace(
                    final_answer="Dexter is a Miami-set crime drama.",
                    halted=False,
                    notices=[],
                )

        fake_module = types.SimpleNamespace(
            AskyClient=FakeAskyClient,
            AskyConfig=lambda **kwargs: kwargs,
            AskyTurnRequest=lambda **kwargs: kwargs,
        )

        with patch("research_context.importlib.import_module", return_value=fake_module):
            result = load_research_context("Dexter: Original Sin", "gf", "web_only")

        self.assertTrue(result.enabled)
        self.assertIn("Miami-set crime drama", result.summary or "")


if __name__ == "__main__":
    unittest.main()
