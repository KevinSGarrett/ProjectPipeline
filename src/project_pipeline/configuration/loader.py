from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from project_pipeline.configuration.models import RuntimeSettings, SecretReference

_ENV_PREFIX = "PROJECT_PIPELINE__"
_LEGACY_ENVIRONMENT_MAP = {
    "PROJECT_PIPELINE_ENVIRONMENT": "environment",
    "PROJECT_PIPELINE_DATA_DIR": "paths.data_dir",
    "PROJECT_PIPELINE_STATE_DIR": "paths.state_dir",
    "PROJECT_PIPELINE_EVIDENCE_DIR": "paths.evidence_dir",
    "PROJECT_PIPELINE_ARTIFACT_DIR": "paths.artifact_dir",
    "PROJECT_PIPELINE_CACHE_DIR": "paths.cache_dir",
    "PROJECT_PIPELINE_LOG_DIR": "paths.log_dir",
    "PROJECT_PIPELINE_LOG_LEVEL": "logging.level",
    "PROJECT_PIPELINE_LOG_FORMAT": "logging.format",
    "PROJECT_PIPELINE_TELEMETRY_ENABLED": "telemetry.enabled",
    "PROJECT_PIPELINE_OTLP_ENDPOINT": "telemetry.otlp_endpoint",
    "PROJECT_PIPELINE_EXTERNAL_WRITE_MODE": "security.external_writes_default",
    "PROJECT_PIPELINE_PERSISTENCE_BACKEND": "persistence.backend",
    "PROJECT_PIPELINE_SQLITE_PATH": "persistence.sqlite_path",
    "PROJECT_PIPELINE_POSTGRESQL_DSN_REF": "persistence.postgresql_dsn",
    "JIRA_BASE_URL": "integrations.jira_base_url",
    "JIRA_USER_EMAIL": "integrations.jira_user_email",
    "JIRA_API_TOKEN_REF": "integrations.jira_api_token",
    "GITHUB_TOKEN_REF": "integrations.github_token",
    "AWS_PROFILE": "integrations.aws_profile",
}
_INTEGRATION_SECRET_FIELDS = ("jira_api_token", "github_token")


class ConfigurationError(RuntimeError):
    """Raised when configuration sources cannot be loaded or validated."""


@dataclass(frozen=True, slots=True)
class EffectiveConfiguration:
    settings: RuntimeSettings
    source_files: tuple[str, ...]
    environment_keys: tuple[str, ...]
    override_keys: tuple[str, ...]

    def redacted_dict(self) -> dict[str, Any]:
        value = self.settings.model_dump(mode="json")
        integrations = value["integrations"]
        for field_name in _INTEGRATION_SECRET_FIELDS:
            reference = getattr(self.settings.integrations, field_name)
            integrations[field_name] = reference.reference if reference else None
        database_reference = self.settings.persistence.postgresql_dsn
        value["persistence"]["postgresql_dsn"] = (
            database_reference.reference if database_reference else None
        )
        return value

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.redacted_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "fingerprint": self.fingerprint(),
            "source_files": list(self.source_files),
            "environment_keys": list(self.environment_keys),
            "override_keys": list(self.override_keys),
            "settings": self.redacted_dict(),
        }


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"invalid environment file entry at {path}:{number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ConfigurationError(f"empty environment key at {path}:{number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(f"configuration file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"invalid JSON configuration at {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigurationError(f"configuration root must be an object: {path}")
    return value


def deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _set_nested(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part.strip().lower() for part in dotted_path.split(".") if part.strip()]
    if not parts:
        raise ConfigurationError("configuration override path cannot be blank")
    cursor = target
    for part in parts[:-1]:
        existing = cursor.get(part)
        if existing is None:
            cursor[part] = {}
        elif not isinstance(existing, dict):
            raise ConfigurationError(f"cannot set nested value beneath scalar key: {part}")
        cursor = cursor[part]
    cursor[parts[-1]] = value


def _environment_overlay(values: Mapping[str, str]) -> tuple[dict[str, Any], list[str]]:
    overlay: dict[str, Any] = {}
    observed: list[str] = []
    for key, raw_value in sorted(values.items()):
        path: str | None = None
        if key.startswith(_ENV_PREFIX):
            path = key.removeprefix(_ENV_PREFIX).lower().replace("__", ".")
        elif key in _LEGACY_ENVIRONMENT_MAP:
            path = _LEGACY_ENVIRONMENT_MAP[key]
        if path is None:
            continue
        observed.append(key)
        _set_nested(overlay, path, _parse_scalar(raw_value))
    return overlay, observed


def _override_overlay(overrides: Sequence[str]) -> tuple[dict[str, Any], list[str]]:
    overlay: dict[str, Any] = {}
    keys: list[str] = []
    for item in overrides:
        if "=" not in item:
            raise ConfigurationError(f"override must use key=value syntax: {item}")
        key, raw_value = item.split("=", 1)
        normalized = key.strip().lower()
        _set_nested(overlay, normalized, _parse_scalar(raw_value))
        keys.append(normalized)
    return overlay, keys


def load_runtime_configuration(
    root: Path,
    *,
    profile: str | None = None,
    config_file: Path | None = None,
    env_file: Path | None = None,
    environment: Mapping[str, str] | None = None,
    overrides: Sequence[str] = (),
) -> EffectiveConfiguration:
    """Load defaults, profile, explicit file, environment, then CLI overrides."""

    root = root.resolve()
    source_environment = dict(os.environ if environment is None else environment)
    file_values = parse_env_file(env_file or root / ".env")
    combined_environment = {**file_values, **source_environment}

    base_path = root / "config" / "runtime" / "base.json"
    base = _load_json_object(base_path)
    selected_profile = (
        profile
        or combined_environment.get("PROJECT_PIPELINE_PROFILE")
        or str(base.get("profile", "local"))
    ).strip()
    if not selected_profile:
        raise ConfigurationError("configuration profile cannot be blank")

    profile_path = root / "config" / "runtime" / "profiles" / f"{selected_profile}.json"
    merged = deep_merge(base, _load_json_object(profile_path))
    merged["profile"] = selected_profile
    sources = [base_path.relative_to(root).as_posix(), profile_path.relative_to(root).as_posix()]

    if config_file is not None:
        resolved = config_file if config_file.is_absolute() else root / config_file
        resolved = resolved.resolve()
        merged = deep_merge(merged, _load_json_object(resolved))
        try:
            sources.append(resolved.relative_to(root).as_posix())
        except ValueError:
            sources.append(str(resolved))

    environment_overlay, environment_keys = _environment_overlay(combined_environment)
    merged = deep_merge(merged, environment_overlay)
    override_overlay, override_keys = _override_overlay(overrides)
    merged = deep_merge(merged, override_overlay)

    try:
        settings = RuntimeSettings.model_validate(merged)
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error
    return EffectiveConfiguration(
        settings=settings,
        source_files=tuple(sources),
        environment_keys=tuple(environment_keys),
        override_keys=tuple(override_keys),
    )


def collect_secret_references(settings: RuntimeSettings) -> tuple[SecretReference, ...]:
    references = (
        settings.integrations.jira_api_token,
        settings.integrations.github_token,
        settings.persistence.postgresql_dsn,
    )
    return tuple(reference for reference in references if reference is not None)
