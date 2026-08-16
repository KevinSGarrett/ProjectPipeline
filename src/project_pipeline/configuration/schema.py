from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from project_pipeline.configuration.models import RuntimeSettings

_SCHEMA_NAME = "runtime_configuration.schema.json"


def runtime_configuration_schema() -> dict[str, Any]:
    schema = RuntimeSettings.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://project-pipeline.local/schemas/{_SCHEMA_NAME}"
    return schema


def write_runtime_configuration_schema(root: Path) -> str:
    path = root / "schemas" / _SCHEMA_NAME
    path.write_text(
        json.dumps(runtime_configuration_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path.relative_to(root).as_posix()


def validate_runtime_configuration_files(root: Path) -> list[str]:
    errors: list[str] = []
    base_path = root / "config" / "runtime" / "base.json"
    profiles = root / "config" / "runtime" / "profiles"
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"runtime base configuration is invalid: {error}"]
    profile_paths = sorted(profiles.glob("*.json"))
    if not profile_paths:
        errors.append("no runtime profiles are defined")
    from project_pipeline.configuration.loader import deep_merge

    for profile_path in profile_paths:
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            merged = deep_merge(base, profile)
            merged["profile"] = profile_path.stem
            RuntimeSettings.model_validate(merged)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            errors.append(f"invalid runtime profile {profile_path.name}: {error}")
    expected = runtime_configuration_schema()
    schema_path = root / "schemas" / _SCHEMA_NAME
    if not schema_path.exists():
        errors.append(f"generated schema is missing: schemas/{_SCHEMA_NAME}")
    else:
        try:
            observed = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            errors.append(f"generated runtime schema is invalid JSON: {error}")
        else:
            if observed != expected:
                errors.append(f"generated schema is stale: schemas/{_SCHEMA_NAME}")
    return errors
