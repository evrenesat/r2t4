from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass, field

DEFAULT_ASKY_RESEARCH_SOURCE_MODE = "web_only"


@dataclass(frozen=True)
class ResearchContextResult:
    enabled: bool
    provider: str | None
    source_mode: str | None
    summary: str | None
    notices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_research_context(
    title_name: str,
    asky_model_alias: str | None,
    asky_research_source_mode: str | None = None,
) -> ResearchContextResult:
    if not asky_model_alias:
        return ResearchContextResult(
            enabled=False,
            provider=None,
            source_mode=None,
            summary=None,
            notices=["asky research not requested."],
        )
    try:
        asky_api = importlib.import_module("asky.api")
    except ImportError:
        return ResearchContextResult(
            enabled=False,
            provider="asky",
            source_mode=asky_research_source_mode or DEFAULT_ASKY_RESEARCH_SOURCE_MODE,
            summary=None,
            notices=["asky is not installed in this environment."],
        )
    source_mode = asky_research_source_mode or DEFAULT_ASKY_RESEARCH_SOURCE_MODE
    try:
        client = asky_api.AskyClient(
            asky_api.AskyConfig(
                model_alias=asky_model_alias,
                research_mode=True,
                summarize=False,
                verbose=False,
                open_browser=False,
            )
        )
        result = client.run_turn(
            asky_api.AskyTurnRequest(
                query_text=build_research_query(title_name),
                research_flag_provided=True,
                research_source_mode=source_mode,
                preload_local_sources=False,
                preload_shortlist=False,
                save_history=False,
            )
        )
    except Exception as error:
        return ResearchContextResult(
            enabled=False,
            provider="asky",
            source_mode=source_mode,
            summary=None,
            notices=[f"asky research failed: {error}"],
        )
    if getattr(result, "halted", False) or not getattr(result, "final_answer", "").strip():
        notices = list(getattr(result, "notices", []) or [])
        if not notices:
            notices = ["asky research returned no answer."]
        return ResearchContextResult(
            enabled=False,
            provider="asky",
            source_mode=source_mode,
            summary=None,
            notices=notices,
        )
    return ResearchContextResult(
        enabled=True,
        provider="asky",
        source_mode=source_mode,
        summary=str(result.final_answer).strip(),
        notices=list(getattr(result, "notices", []) or []),
    )


def build_research_query(title_name: str) -> str:
    return (
        f"Provide a compact factual brief for the title '{title_name}'. "
        "Focus on setting, named characters, key relationships, and premise details "
        "that would help correct scene-level narrative summaries. "
        "Do not include spoilers beyond what is necessary to identify the title."
    )
