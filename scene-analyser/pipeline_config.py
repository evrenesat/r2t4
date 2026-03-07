from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config/pipeline.toml")
DEFAULT_SUMMARY_GATE = "start_when_ready"
VALID_SUMMARY_GATES = {"start_when_ready", "wait_for_all_summaries"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class ApiConfig:
    url: str
    api_key_env: str | None = None
    api_key: str | None = None

    def get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env is None:
            return ""
        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise ConfigError(
                f"Environment variable '{self.api_key_env}' is not set for provider '{self.url}'."
            )
        return api_key


@dataclass(frozen=True)
class ModelConfig:
    id: str
    api: str
    context_size: int
    image_support: bool = True


@dataclass(frozen=True)
class ResolvedModelConfig:
    id: str
    api_url: str
    api_key: str
    context_size: int
    image_support: bool
    api_name: str


@dataclass(frozen=True)
class ExecutionConfig:
    summary_gate: str = DEFAULT_SUMMARY_GATE


@dataclass(frozen=True)
class ExtractorConfig:
    video_path: str | None = None
    output_dir: str = "output"
    preset: str = "balanced"
    enable_diagnostics: bool = True


@dataclass(frozen=True)
class SubtitleIngestionConfig:
    subtitle_language: str = "eng"
    subtitle_stream_index: int | None = None
    allow_subliminal_download: bool = True


@dataclass(frozen=True)
class SubtitleSummaryConfig:
    recent_window_count: int = 3
    normalized_transcript_filename: str = "normalized_transcript.txt"
    contexts_dirname: str = "contexts"
    summary_cache_filename: str = "subtitle_summaries.jsonl"
    row_poll_interval_sec: float = 0.2
    row_wait_timeout_sec: float = 300.0


@dataclass(frozen=True)
class SceneInferenceConfig:
    strategy: str = "image_with_precomputed_subtitle_context"


@dataclass(frozen=True)
class ArtifactConfig:
    max_validation_retries: int = 2


def _merge_section(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = base.copy()
    merged.update(override)
    return merged


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class PipelineConfig:
    def __init__(self, toml_path: Path = CONFIG_PATH, profile: str = "default") -> None:
        if not toml_path.exists():
            raise FileNotFoundError(f"Config file not found: {toml_path}")
        with toml_path.open("rb") as handle:
            self._data = tomllib.load(handle)

        self.path = toml_path
        self.profile_name = profile
        self.apis = {key: ApiConfig(**value) for key, value in self._data.get("api", {}).items()}
        self.models = {
            key: ModelConfig(**value) for key, value in self._data.get("models", {}).items()
        }

        profiles = self._data.get("profiles", {})
        profile_data = profiles.get(profile, {})
        if profiles and profile not in profiles and profile != "default":
            raise ConfigError(f"Profile '{profile}' not found in {toml_path}.")

        self.roles = _merge_section(self._data.get("roles", {}), profile_data.get("roles", {}))

        execution_values = _merge_section(
            self._data.get("execution", {}), profile_data.get("execution", {})
        )
        self.execution_config = ExecutionConfig(**execution_values)
        if self.execution_config.summary_gate not in VALID_SUMMARY_GATES:
            raise ConfigError(
                f"Unsupported summary_gate '{self.execution_config.summary_gate}'. "
                f"Expected one of {sorted(VALID_SUMMARY_GATES)}."
            )
        self.execution = asdict(self.execution_config)

        extractor_values = _merge_section(
            self._data.get("extractor", {}), profile_data.get("extractor", {})
        )
        extractor_values["video_path"] = _normalize_optional_string(
            extractor_values.get("video_path")
        )
        self.extractor_config = ExtractorConfig(**extractor_values)
        self.extractor = asdict(self.extractor_config)

        subtitle_ingestion_values = _merge_section(
            self._data.get("subtitle_ingestion", {}),
            profile_data.get("subtitle_ingestion", {}),
        )
        self.subtitle_ingestion_config = SubtitleIngestionConfig(**subtitle_ingestion_values)
        self.subtitle_ingestion = asdict(self.subtitle_ingestion_config)

        subtitle_summary_values = _merge_section(
            self._data.get("subtitle_summary", {}),
            profile_data.get("subtitle_summary", {}),
        )
        self.subtitle_summary_config = SubtitleSummaryConfig(**subtitle_summary_values)
        self.subtitle_summary = asdict(self.subtitle_summary_config)

        scene_inference_values = _merge_section(
            self._data.get("scene_inference", {}),
            profile_data.get("scene_inference", {}),
        )
        self.scene_inference_config = SceneInferenceConfig(**scene_inference_values)
        self.scene_inference = asdict(self.scene_inference_config)

        artifact_values = _merge_section(
            self._data.get("artifact", {}), profile_data.get("artifact", {})
        )
        self.artifact_config = ArtifactConfig(**artifact_values)
        self.artifact = asdict(self.artifact_config)

    def resolve_model(self, alias: str) -> ResolvedModelConfig:
        model_cfg = self.models.get(alias)
        if model_cfg is None:
            raise ConfigError(f"Model alias '{alias}' not found in config.")
        api_cfg = self.apis.get(model_cfg.api)
        if api_cfg is None:
            raise ConfigError(f"API section '{model_cfg.api}' not found for model '{alias}'.")
        return ResolvedModelConfig(
            id=model_cfg.id,
            api_url=api_cfg.url,
            api_key=api_cfg.get_api_key(),
            context_size=model_cfg.context_size,
            image_support=model_cfg.image_support,
            api_name=model_cfg.api,
        )

    def get_role_model(self, role: str) -> ResolvedModelConfig:
        alias = self.roles.get(role)
        if not alias:
            raise ConfigError(f"Role '{role}' is not configured.")
        return self.resolve_model(alias)

    def resolve_video_path(self, override: Path | None = None) -> Path:
        if override is not None:
            return override
        configured = _normalize_optional_string(self.extractor_config.video_path)
        if configured is None:
            raise ConfigError(
                "No video path configured. Set extractor.video_path in config/pipeline.toml "
                "or pass --video-path."
            )
        return Path(configured)
