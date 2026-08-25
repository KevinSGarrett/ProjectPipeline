"""Constrained, non-secret runtime configuration for autonomous campaigns."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.configuration.loader import (
    ConfigurationError,
    load_runtime_configuration,
    parse_env_file,
)
from project_pipeline.configuration.models import SecretReference

_CAMPAIGN_RUNTIME_KEYS = frozenset(
    {
        "JIRA_BASE_URL",
        "JIRA_USER_EMAIL",
        "JIRA_API_TOKEN_REF",
        "GITHUB_TOKEN_REF",
        "CAMPAIGN_PROJECT_ID",
        "CAMPAIGN_CYCLE_ID",
        "CAMPAIGN_MACHINE_ID",
        "CAMPAIGN_PRINCIPAL_SID",
        "CAMPAIGN_LEASE_ID",
        "CAMPAIGN_LEASE_EXPIRES_AT_UTC",
        "CAMPAIGN_DEADLINE_AT_UTC",
    }
)
_SCOPE_ENVIRONMENT_KEYS = {
    "project_id": "CAMPAIGN_PROJECT_ID",
    "cycle_id": "CAMPAIGN_CYCLE_ID",
    "machine_id": "CAMPAIGN_MACHINE_ID",
    "identity_id": "CAMPAIGN_PRINCIPAL_SID",
    "lease_id": "CAMPAIGN_LEASE_ID",
    "expires_at_utc": "CAMPAIGN_LEASE_EXPIRES_AT_UTC",
}
_C16B_LEASE_MINIMUM = timedelta(days=5)
_C16B_LEASE_MAXIMUM = timedelta(days=7)
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


def campaign_secret_scope(
    environment: Mapping[str, str],
    *,
    require_fresh_campaign_window: bool = False,
    allow_expired: bool = False,
) -> dict[str, str]:
    """Return the exact non-secret scope that authorizes a Cycle 16-B DPAPI envelope.

    Admission and provisioning require a newly issued bounded lease.  Recovery
    and ordinary runtime resolution instead require an unexpired lease: the
    100-hour ladder must not make a valid already-bound lease unusable simply
    because its initial issuance window has passed.
    """

    scope = {
        key: str(environment.get(source) or "").strip()
        for key, source in _SCOPE_ENVIRONMENT_KEYS.items()
    }
    if not all(scope.values()):
        raise ConfigurationError("campaign runtime environment lacks a complete credential scope")
    if scope["project_id"] != "PROJECT-PIPELINE" or scope["cycle_id"] != "CYCLE-16-B":
        raise ConfigurationError(
            "campaign credential scope is not bound to ProjectPipeline Cycle 16-B"
        )
    if not re.fullmatch(r"S-\d+(?:-\d+)+", scope["identity_id"]):
        raise ConfigurationError(
            "campaign credential scope requires a canonical Windows principal SID"
        )
    if not re.fullmatch(r"SLEASE-[A-Za-z0-9-]+", scope["lease_id"]):
        raise ConfigurationError("campaign credential scope contains an invalid lease identity")
    try:
        expiry = datetime.fromisoformat(scope["expires_at_utc"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ConfigurationError("campaign credential lease expiry is invalid") from error
    if expiry.tzinfo is None:
        raise ConfigurationError("campaign credential lease expiry must be UTC-aware")
    remaining = expiry - datetime.now(UTC)
    if remaining <= timedelta(0) and not allow_expired:
        raise ConfigurationError("campaign credential lease is expired")
    if require_fresh_campaign_window and not (
        _C16B_LEASE_MINIMUM <= remaining <= _C16B_LEASE_MAXIMUM
    ):
        raise ConfigurationError(
            "campaign credential lease does not cover a fresh Cycle 16-B admission window"
        )
    return scope


def _parse_utc_timestamp(value: str, *, label: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConfigurationError(f"{label} is invalid") from error
    if timestamp.tzinfo is None:
        raise ConfigurationError(f"{label} must be UTC-aware")
    return timestamp


def campaign_lease_deadline(environment: Mapping[str, str]) -> datetime:
    """Require the bound credential lease to extend through campaign completion."""

    scope = campaign_secret_scope(environment)
    deadline_value = str(environment.get("CAMPAIGN_DEADLINE_AT_UTC") or "").strip()
    if not deadline_value:
        raise ConfigurationError("campaign runtime environment lacks a campaign deadline")
    deadline = _parse_utc_timestamp(deadline_value, label="campaign deadline")
    if deadline <= datetime.now(UTC):
        raise ConfigurationError("campaign deadline is expired")
    expiry = _parse_utc_timestamp(scope["expires_at_utc"], label="campaign credential lease expiry")
    if expiry < deadline:
        raise ConfigurationError(
            "campaign credential lease expires before the bound campaign deadline"
        )
    return deadline


def load_campaign_runtime_environment(
    root: Path, env_file: Path, *, require_fresh_campaign_window: bool = False
) -> dict[str, str]:
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
    jira_reference = SecretReference(reference=values["JIRA_API_TOKEN_REF"])
    github_reference = SecretReference(reference=values["GITHUB_TOKEN_REF"])
    if jira_reference.scheme != "dpapi":
        raise ConfigurationError("campaign Jira credential must use a current-user DPAPI reference")
    if github_reference.reference != "gh-auth://default":
        raise ConfigurationError(
            "campaign GitHub credential must use the authenticated GitHub CLI reference"
        )
    campaign_secret_scope(values, require_fresh_campaign_window=require_fresh_campaign_window)
    campaign_lease_deadline(values)
    return {key: values[key] for key in sorted(values)}


def apply_campaign_runtime_environment(
    root: Path, env_file: Path, *, require_fresh_campaign_window: bool = False
) -> dict[str, str]:
    """Apply validated references to this process only; no secret is materialized."""

    values = load_campaign_runtime_environment(
        root, env_file, require_fresh_campaign_window=require_fresh_campaign_window
    )
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
