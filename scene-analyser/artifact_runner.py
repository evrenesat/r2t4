from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline_config import PipelineConfig, ResolvedModelConfig
from openai_compatible_client import CompletionFailure, CompletionSuccess, OpenAICompatibleClient
from research_context import load_research_context
from subtitle_ingestion import load_subtitles
from tdt_format import TDT_FILENAME, TDT_FORMAT_ID, TDT_FORMAT_NAME, TDT_FORMAT_VERSION, validate_tdt

LOGGER = logging.getLogger(__name__)

ARTIFACT_PROMPTS_PATH = Path("artifact_prompts.md")
ARTIFACT_RUNS_DIRNAME = "artifact_runs"
ARTIFACT_RUN_METADATA_FILENAME = "run.json"
DEFAULT_ARTIFACT_MAX_VALIDATION_RETRIES = 2


@dataclass(frozen=True)
class ArtifactRunConfig:
    inference_run_dir: Path
    config_path: Path
    profile: str
    title_name: str | None
    asky_research_source_mode: str | None
    max_validation_retries: int
    allow_partial_analysis: bool


def parse_args() -> ArtifactRunConfig:
    parser = argparse.ArgumentParser(
        description="Generate a Timed Descriptive Transcript from one completed inference run."
    )
    parser.add_argument("--inference-run-dir", required=True)
    parser.add_argument("--config", default="config/pipeline.toml")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--title-name")
    parser.add_argument("--asky-research-source-mode")
    parser.add_argument(
        "--max-validation-retries",
        type=int,
        default=DEFAULT_ARTIFACT_MAX_VALIDATION_RETRIES,
    )
    parser.add_argument("--allow-partial-analysis", action="store_true")
    args = parser.parse_args()
    return ArtifactRunConfig(
        inference_run_dir=Path(args.inference_run_dir),
        config_path=Path(args.config),
        profile=args.profile,
        title_name=args.title_name,
        asky_research_source_mode=args.asky_research_source_mode,
        max_validation_retries=args.max_validation_retries,
        allow_partial_analysis=args.allow_partial_analysis,
    )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_artifact_prompt(prompts_path: Path = ARTIFACT_PROMPTS_PATH) -> tuple[str, str]:
    prompt_text = prompts_path.read_text(encoding="utf-8").strip()
    digest = hashlib.sha1(prompt_text.encode("utf-8")).hexdigest()[:12]
    return prompt_text, f"artifact_prompts_md_{digest}"


def create_artifact_run_dir(inference_run_dir: Path, model_id: str) -> Path:
    base_dir = inference_run_dir / ARTIFACT_RUNS_DIRNAME
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = base_dir / f"{timestamp}_timed_descriptive_transcript_{sanitize_slug(model_id)}"
    variant = 2
    while run_dir.exists():
        run_dir = base_dir / (
            f"{timestamp}_timed_descriptive_transcript_{sanitize_slug(model_id)}_v{variant}"
        )
        variant += 1
    run_dir.mkdir()
    return run_dir


def sanitize_slug(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "run"


def derive_title_name(override: str | None, video_path: str | None, inference_run_dir: Path) -> str:
    if override:
        return override
    if video_path:
        return Path(video_path).stem
    return inference_run_dir.name


def collect_expected_segments(
    result_rows: list[dict[str, Any]],
    allow_partial_analysis: bool,
) -> list[dict[str, Any]]:
    if not allow_partial_analysis:
        failed_rows = [row for row in result_rows if not isinstance(row.get("analysis"), dict)]
        if failed_rows:
            raise ValueError(
                "Artifact generation requires successful analyses for every scene window unless "
                "--allow-partial-analysis is set."
            )
    return [
        {
            "grid_filename": row["grid_filename"],
            "chunk_start": row["chunk_start"],
            "chunk_end": row["chunk_end"],
        }
        for row in result_rows
    ]


def build_artifact_input_bundle(
    source_run_metadata: dict[str, Any],
    result_rows: list[dict[str, Any]],
    subtitle_events: list[dict[str, Any]],
    title_name: str,
    research_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title_name": title_name,
        "source_run_metadata": {
            "grid_run_dir": source_run_metadata.get("grid_run_dir"),
            "video_path": source_run_metadata.get("video_path"),
            "strategy": source_run_metadata.get("strategy"),
            "model_aliases": source_run_metadata.get("model_aliases", {}),
            "subtitle_source": source_run_metadata.get("subtitle_source"),
            "selection_window": source_run_metadata.get("selection_window"),
        },
        "scene_rows": [
            {
                "grid_filename": row["grid_filename"],
                "chunk_start": row["chunk_start"],
                "chunk_end": row["chunk_end"],
                "analysis": row.get("analysis"),
                "subtitle_context": row.get("subtitle_context"),
                "error": row.get("error"),
            }
            for row in result_rows
        ],
        "subtitle_events": subtitle_events,
        "research_context": research_context,
    }


def filter_subtitle_events_for_rows(
    subtitle_events: list[Any],
    result_rows: list[dict[str, Any]],
) -> list[Any]:
    if not result_rows:
        return []
    min_start = min(float(row["chunk_start"]) for row in result_rows)
    max_end = max(float(row["chunk_end"]) for row in result_rows)
    return [
        event
        for event in subtitle_events
        if float(event.start) <= max_end and float(event.end) >= min_start
    ]


def build_artifact_user_text(
    input_bundle: dict[str, Any],
    previous_errors: list[str] | None,
) -> str:
    error_block = ""
    if previous_errors:
        error_block = (
            "\nPrevious attempt validation errors:\n- "
            + "\n- ".join(previous_errors)
            + "\nFix all of them in the next response."
        )
    return (
        "Generate a Timed Descriptive Transcript (TDT) JSON artifact from the following input.\n"
        "Keep the output aligned to the supplied scene windows and subtitle indexes."
        f"{error_block}\n\n"
        "Input bundle:\n"
        f"{json.dumps(input_bundle, indent=2, ensure_ascii=True)}"
    )


def build_artifact_run_metadata(
    config: ArtifactRunConfig,
    source_run_metadata: dict[str, Any],
    prompt_version: str,
    research_context: dict[str, Any],
    attempts: list[dict[str, Any]],
    status: str,
    artifact_path: str | None,
    artifact_model_config: ResolvedModelConfig,
    pipeline_config: PipelineConfig,
) -> dict[str, Any]:
    model_aliases = source_run_metadata.get("model_aliases", {})
    return {
        "format_name": TDT_FORMAT_NAME,
        "format": TDT_FORMAT_ID,
        "format_version": TDT_FORMAT_VERSION,
        "inference_run_dir": str(config.inference_run_dir),
        "source_grid_run_dir": source_run_metadata.get("grid_run_dir"),
        "source_strategy": source_run_metadata.get("strategy"),
        "source_model_aliases": model_aliases,
        "config_profile": config.profile,
        "artifact_model_alias": pipeline_config.roles.get("artifact_model"),
        "provider_api": artifact_model_config.api_name,
        "artifact_model": artifact_model_config.id,
        "chat_completions_url": artifact_model_config.api_url,
        "prompt_version": prompt_version,
        "research_context": research_context,
        "max_validation_retries": config.max_validation_retries,
        "allow_partial_analysis": config.allow_partial_analysis,
        "attempts": attempts,
        "status": status,
        "artifact_path": artifact_path,
    }


async def run_artifact_generation(config: ArtifactRunConfig) -> Path:
    pipeline_config = PipelineConfig(config.config_path, config.profile)
    artifact_model_alias = pipeline_config.roles.get("artifact_model")
    if not artifact_model_alias:
        raise ValueError("Role 'artifact_model' is not configured.")
    artifact_model_config = pipeline_config.resolve_model(artifact_model_alias)

    source_run_metadata = load_json(config.inference_run_dir / "run.json")
    result_rows = load_jsonl(config.inference_run_dir / "results.jsonl")
    expected_segments = collect_expected_segments(
        result_rows=result_rows,
        allow_partial_analysis=config.allow_partial_analysis,
    )
    title_name = derive_title_name(
        override=config.title_name,
        video_path=source_run_metadata.get("video_path"),
        inference_run_dir=config.inference_run_dir,
    )
    grid_run_dir = Path(str(source_run_metadata["grid_run_dir"]))
    subtitle_source = source_run_metadata.get("subtitle_source") or {}
    loaded_subtitle_source, subtitle_events = load_subtitles(
        video_path=Path(str(source_run_metadata["video_path"]))
        if source_run_metadata.get("video_path")
        else None,
        grid_run_dir=grid_run_dir,
        subtitle_language=str(subtitle_source.get("language") or "eng"),
        subtitle_stream_index=subtitle_source.get("stream_index"),
    )
    subtitle_events = filter_subtitle_events_for_rows(subtitle_events, result_rows)
    
    asky_model_alias = pipeline_config.roles.get("research_model") or artifact_model_alias
    
    research_context = load_research_context(
        title_name=title_name,
        asky_model_alias=asky_model_alias,
        asky_research_source_mode=config.asky_research_source_mode,
    ).to_dict()
    prompt_text, prompt_version = load_artifact_prompt()
    input_bundle = build_artifact_input_bundle(
        source_run_metadata=source_run_metadata,
        result_rows=result_rows,
        subtitle_events=[event.to_dict() for event in subtitle_events],
        title_name=title_name,
        research_context=research_context,
    )
    run_dir = create_artifact_run_dir(config.inference_run_dir, artifact_model_config.id)
    run_metadata_path = run_dir / ARTIFACT_RUN_METADATA_FILENAME
    
    client = OpenAICompatibleClient()
    
    attempts: list[dict[str, Any]] = []
    previous_errors: list[str] | None = None
    artifact_path = run_dir / TDT_FILENAME
    write_json(
        run_metadata_path,
        build_artifact_run_metadata(
            config=config,
            source_run_metadata=source_run_metadata,
            prompt_version=prompt_version,
            research_context=research_context,
            attempts=attempts,
            status="running",
            artifact_path=None,
            artifact_model_config=artifact_model_config,
            pipeline_config=pipeline_config,
        ),
    )
    max_attempts = config.max_validation_retries + 1
    for attempt_number in range(1, max_attempts + 1):
        completion = await client.generate_json(
            model_alias=artifact_model_alias,
            system_prompt=prompt_text,
            user_text=build_artifact_user_text(input_bundle, previous_errors),
            config=pipeline_config,
        )
        attempt_record = {"attempt": attempt_number}
        if isinstance(completion, CompletionFailure):
            previous_errors = [f"{completion.error_type}: {completion.message}"]
            attempt_record.update(
                {
                    "ok": False,
                    "completion": completion.to_dict(),
                    "validation_errors": previous_errors,
                }
            )
            attempts.append(attempt_record)
            write_json(
                run_metadata_path,
                build_artifact_run_metadata(
                    config=config,
                    source_run_metadata=source_run_metadata,
                    prompt_version=prompt_version,
                    research_context=research_context,
                    attempts=attempts,
                    status="running",
                    artifact_path=None,
                    artifact_model_config=artifact_model_config,
                    pipeline_config=pipeline_config,
                ),
            )
            continue
        candidate = completion.parsed_json
        validation_errors = validate_tdt(candidate, expected_segments=expected_segments)
        if not validation_errors:
            candidate["generation"] = {
                **(candidate.get("generation", {}) if isinstance(candidate.get("generation"), dict) else {}),
                "artifact_model": artifact_model_config.id,
                "artifact_model_alias": artifact_model_alias,
                "provider_api": artifact_model_config.api_name,
                "source_inference_model_aliases": source_run_metadata.get("model_aliases", {}),
                "source_subtitle_source": loaded_subtitle_source.to_dict(),
                "prompt_version": prompt_version,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
            write_json(artifact_path, candidate)
            attempt_record.update(
                {
                    "ok": True,
                    "completion": completion.to_dict(),
                    "validation_errors": [],
                }
            )
            attempts.append(attempt_record)
            write_json(
                run_metadata_path,
                build_artifact_run_metadata(
                    config=config,
                    source_run_metadata=source_run_metadata,
                    prompt_version=prompt_version,
                    research_context=research_context,
                    attempts=attempts,
                    status="completed",
                    artifact_path=str(artifact_path),
                    artifact_model_config=artifact_model_config,
                    pipeline_config=pipeline_config,
                ),
            )
            return run_dir
        previous_errors = validation_errors
        attempt_record.update(
            {
                "ok": False,
                "completion": completion.to_dict(),
                "validation_errors": validation_errors,
            }
        )
        attempts.append(attempt_record)
        write_json(
            run_metadata_path,
            build_artifact_run_metadata(
                config=config,
                source_run_metadata=source_run_metadata,
                prompt_version=prompt_version,
                research_context=research_context,
                attempts=attempts,
                status="running",
                artifact_path=None,
                artifact_model_config=artifact_model_config,
                pipeline_config=pipeline_config,
            ),
        )
    write_json(
        run_metadata_path,
        build_artifact_run_metadata(
            config=config,
            source_run_metadata=source_run_metadata,
            prompt_version=prompt_version,
            research_context=research_context,
            attempts=attempts,
            status="failed",
            artifact_path=None,
            artifact_model_config=artifact_model_config,
            pipeline_config=pipeline_config,
        ),
    )
    raise ValueError(
        f"Artifact generation failed validation after "
        f"{max_attempts} attempts: {previous_errors or ['unknown error']} "
        f"(provider: {artifact_model_config.api_name}, alias: {artifact_model_alias})"
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    configure_logging()
    config = parse_args()
    run_dir = asyncio.run(run_artifact_generation(config))
    LOGGER.info("Artifact output written to %s", run_dir)


if __name__ == "__main__":
    main()
