"""Constrained, non-secret runtime configuration for autonomous campaigns."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path

from project_pipeline.configuration.loader import (
    ConfigurationError,
    load_runtime_configuration,
    parse_env_file,
)


_CAMPAIGN_RUNTIME_KEYS = frozenset(
    {"JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_API_TOKEN_REF", "GITHUB_TOKEN_REF"}
)
_PROCESS_PASSTHROUGH_KEYS = (
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "USERNAME",
    "USERDOMAIN",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "TEMP",
    "TMP",
)


def load_campaign_runtime_environment(root: Path, env_file: Path) -> dict[str, str]:
    """Read one non-secret allowlisted environment file for a bound campaign."""

    root = root.resolve()
    env_file = env_file.resolve()
    if not env_file.is_file():
        raise ConfigurationError("campaign runtime environment file is unavailable")
    values = parse_env_file(env_file)
    unknown = sorted(set(values) - _CAMPAIGN_RUNTIME_KEYS)
    if unknown:
        raise ConfigurationError("campaign runtime environment contains disallowed keys")
    configuration = load_runtime_configuration(root, environment=values)
    integrations = configuration.settings.integrations
    if (
        not integrations.jira_base_url
        or not integrations.jira_user_email
        or not integrations.jira_api_token
    ):
        raise ConfigurationError("campaign runtime environment lacks a complete Jira reference")
    if not integrations.github_token:
        raise ConfigurationError("campaign runtime environment lacks a GitHub reference")
    return {key: values[key] for key in sorted(values)}


def apply_campaign_runtime_environment(root: Path, env_file: Path) -> dict[str, str]:
    """Apply validated references to this process only; no secret is materialized."""

    values = load_campaign_runtime_environment(root, env_file)
    os.environ.update(values)
    return values


def limited_campaign_subprocess_environment(
    root: Path, env_file: Path, *, source: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Construct the recovery child environment from an explicit allowlist."""

    parent = os.environ if source is None else source
    values = load_campaign_runtime_environment(root, env_file)
    result = {key: parent[key] for key in _PROCESS_PASSTHROUGH_KEYS if parent.get(key)}
    result.update(values)
    result["PYTHONPATH"] = str(root.resolve() / "src")
    result["PYTHONUTF8"] = "1"
    return result
