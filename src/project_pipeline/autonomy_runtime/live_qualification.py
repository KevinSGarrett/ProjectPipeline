from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    qualify_cursor_cli_provider,
    remove_disposable_workspace,
)
from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.providers import (
    AutonomyProviderRuntime,
    BudgetDecision,
    local_test_provider,
)
from project_pipeline.autonomy_runtime.recheck import AutonomousRecheckStore
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor
from project_pipeline.autonomy_runtime.windows_service import (
    AutonomyRuntimeWindowsService,
    build_paths,
    plan_service_commands,
)
from project_pipeline.command_center.autonomy import project_autonomy_runtime
from project_pipeline.lifecycle.attestation_recovery import (
    EXPECTED_PUBLIC_ATTESTATION_BYTES,
    EXPECTED_PUBLIC_ATTESTATION_SHA256,
    EXPECTED_PUBLIC_QUALIFICATION_BYTES,
    EXPECTED_PUBLIC_QUALIFICATION_SHA256,
    PUBLIC_ATTESTATION_REF,
    PUBLIC_QUALIFICATION_REF,
    load_current_attestation_policy,
)


class StageOutcome(StrEnum):
    PASSED = "PASSED"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    FAILED = "FAILED"


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    outcome: StageOutcome
    observations: dict[str, Any]
    reasons: tuple[str, ...] = ()

    def projected_outcome(self) -> StageOutcome:
        return self.outcome

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "outcome": self.projected_outcome().value,
            "observations": self.observations,
            "reasons": list(self.reasons),
        }


CURSOR_CLI_ATTESTATION_REF = "evidence/pp379_writer_attestation_evidence.json"
CURSOR_CLI_QUALIFICATION_REF = "evidence/pp379_writer_provider_qualification_evidence.json"
_SERVICE_PLAN_KEYS = ("install", "start", "stop", "restart", "uninstall", "status")
_DEFAULT_REPOSITORY_SLUG = "KevinSGarrett/ProjectPipeline"
_LIVE_QUAL_JIRA_LOCAL_ID = "PP-TASK-000384"
_LIVE_QUAL_PROBE_MARKER = "PP384-LIVE-QUAL-PROBE"
_GITHUB_PROBE_BRANCH = "qual/pp384-live-probe"
_ALLOWED_GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})
_GITHUB_BRANCH_DELETE_READBACK_ATTEMPTS = 5
_CAMPAIGN_IDENTITY_KEYS = frozenset(
    {
        "CAMPAIGN_PROJECT_ID",
        "CAMPAIGN_CYCLE_ID",
        "CAMPAIGN_MACHINE_ID",
        "CAMPAIGN_PRINCIPAL_SID",
        "CAMPAIGN_ID",
        "CAMPAIGN_CANDIDATE_SHA",
        "CAMPAIGN_CANDIDATE_TREE",
        "CAMPAIGN_SCHEDULER_LEASE_ID",
        "CAMPAIGN_FENCE_TOKEN",
        "CAMPAIGN_CREDENTIAL_ENVELOPE_EXPIRES_AT_UTC",
        "CAMPAIGN_DEADLINE_AT_UTC",
    }
)
_GITHUB_BRANCH_DELETE_READBACK_DELAY_SECONDS = 0.2
_COORDINATOR_JIRA_RECEIPT_KIND = "pp384_coordinator_jira_governance"
_COORDINATOR_JIRA_RECEIPT_VERSION = "1.0.0"
_COORDINATOR_JIRA_RECEIPT_MAX_AGE = timedelta(minutes=15)
_PRIMARY_COORDINATOR_ID = "PRIMARY-CODEX-WORKSTATION"
_COORDINATOR_JIRA_SIGNATURE_NAMESPACE = "project-pipeline-pp384-jira-governance"
_COORDINATOR_JIRA_ALLOWED_SIGNERS = Path("config/security/coordinator_jira_receipt_allowed_signers")
_COORDINATOR_ATTESTATION_RECEIPT_KIND = "pp384_coordinator_attestation_relay"
_COORDINATOR_ATTESTATION_RECEIPT_VERSION = "1.0.0"
_COORDINATOR_ATTESTATION_SIGNATURE_NAMESPACE = "project-pipeline-pp384-attestation"


def _github_repository_slug_from_url(url: str) -> str | None:
    value = url.strip()
    if not value:
        return None
    if value.startswith("git@github.com:"):
        slug = value.split(":", 1)[1].strip()
        if slug.endswith(".git"):
            slug = slug[:-4]
        slug = slug.strip("/")
        if slug.count("/") == 1 and all(part for part in slug.split("/", 1)):
            return slug
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.hostname
    if host is None or host.lower() not in _ALLOWED_GITHUB_HOSTS:
        return None
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if path.count("/") != 1:
        return None
    owner, repo = path.split("/", 1)
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _coordinator_jira_receipt_digest(payload: dict[str, Any]) -> str:
    """Hash the canonical receipt body, excluding its self-declared address."""

    unsigned = dict(payload)
    unsigned.pop("receipt_sha256", None)
    return _digest(unsigned)


def _coordinator_jira_receipt_message(receipt_sha256: str) -> bytes:
    return f"sha256:{receipt_sha256}\n".encode("ascii")


def _run_gh_json(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "exit_code": None}
    if completed.returncode != 0:
        return {"ok": False, "exit_code": completed.returncode}
    raw = completed.stdout.strip()
    if not raw:
        return {"ok": False, "exit_code": completed.returncode, "parse_error": True}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": True, "payload": raw.strip('"')}
    return {"ok": True, "payload": payload}


def _gh_auth_available() -> bool:
    try:
        completed = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _credential_environment(repository_root: Path) -> dict[str, str]:
    """Load legacy files only as defaults; process-bound campaign refs take precedence."""

    from project_pipeline.configuration.campaign_environment import (
        campaign_runtime_environment_from_process,
    )
    from project_pipeline.configuration.loader import parse_env_file

    process_environment = dict(os.environ)
    # A scheduled campaign receives its constrained, non-secret runtime
    # environment directly.  Do not load a mutable checkout or coordinator
    # .env in that context, even as a fallback.
    if _CAMPAIGN_IDENTITY_KEYS.intersection(process_environment):
        campaign_environment = campaign_runtime_environment_from_process(
            repository_root, source=process_environment
        )
        if campaign_environment is None:
            raise RuntimeError("campaign runtime environment is unavailable")
        return campaign_environment
    merged: dict[str, str] = {}
    project_json = repository_root / "config" / "project.json"
    if project_json.is_file():
        target_root = json.loads(project_json.read_text(encoding="utf-8")).get("target_local_root")
        if isinstance(target_root, str) and target_root.strip():
            canonical_env = Path(target_root).expanduser().resolve() / ".env"
            if canonical_env.is_file():
                merged.update(parse_env_file(canonical_env))
    merged.update(parse_env_file(repository_root / ".env"))
    # The recovery runner supplies validated references through its constrained
    # process environment.  A mutable checkout .env must never replace them.
    merged.update(os.environ)
    return merged


def _resolve_github_token(repository_root: Path) -> tuple[str | None, str]:
    from project_pipeline.configuration.campaign_environment import (
        validate_campaign_runtime_binding,
    )
    from project_pipeline.configuration.loader import ConfigurationError, load_runtime_configuration
    from project_pipeline.configuration.secrets import (
        SecretResolver,
        issue_campaign_secret_access_lease,
    )

    environment = _credential_environment(repository_root)
    campaign_environment_declared = bool(_CAMPAIGN_IDENTITY_KEYS.intersection(environment))
    if campaign_environment_declared:
        try:
            configuration = load_runtime_configuration(
                repository_root, environment=environment, include_default_env_file=False
            )
            token_ref = configuration.settings.integrations.github_token
            if token_ref is None:
                return None, "none"
            if token_ref.reference != "dpapi://C16B_GITHUB_TOKEN":
                return None, "none"
            required_scope = validate_campaign_runtime_binding(repository_root, environment)
            access_lease = issue_campaign_secret_access_lease(
                repository_root,
                required_scope,
                access_identity=f"live-qualification-github:{os.getpid()}",
            )
            token = SecretResolver(
                repository_root,
                environment,
                required_scope=required_scope,
                access_lease=access_lease,
            ).resolve(token_ref)
            return (token, "campaign-dpapi") if token.strip() else (None, "none")
        except (ConfigurationError, RuntimeError):
            return None, "none"

    completed: subprocess.CompletedProcess[str] | None = None
    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        # A normal coordinator may have a configured secret reference even
        # when the optional GitHub CLI is unavailable.  Only the campaign
        # route is constrained to its DPAPI-bound reference above.
        completed = None
    if completed is not None and completed.returncode == 0:
        token = completed.stdout.strip()
        if token:
            return token, "gh-auth"

    try:
        configuration = load_runtime_configuration(repository_root, environment=environment)
        token_ref = configuration.settings.integrations.github_token
        if token_ref is None:
            return None, "none"
        token = SecretResolver(repository_root, environment).resolve(token_ref)
        if token.strip():
            return token, "config"
    except (ConfigurationError, RuntimeError):
        return None, "none"
    return None, "none"


def _build_jira_adapter(repository_root: Path) -> Any:
    from project_pipeline.configuration.campaign_environment import (
        validate_campaign_runtime_binding,
    )
    from project_pipeline.configuration.loader import load_runtime_configuration
    from project_pipeline.configuration.secrets import (
        SecretResolver,
        issue_campaign_secret_access_lease,
    )
    from project_pipeline.jira_steward.adapter import AtlassianJiraCloudAdapter

    environment = _credential_environment(repository_root)
    campaign_environment_declared = bool(_CAMPAIGN_IDENTITY_KEYS.intersection(environment))
    configuration = load_runtime_configuration(
        repository_root,
        environment=environment,
        include_default_env_file=not campaign_environment_declared,
    )
    integrations = configuration.settings.integrations
    if not integrations.jira_base_url or not integrations.jira_user_email:
        raise RuntimeError("jira_integration_not_configured")
    if integrations.jira_api_token is None:
        raise RuntimeError("jira_api_token_unconfigured")
    required_scope = None
    access_lease = None
    if integrations.jira_api_token.scheme == "dpapi":
        if not campaign_environment_declared:
            raise RuntimeError("campaign_dpapi_jira_requires_a_bound_runtime_environment")
        required_scope = validate_campaign_runtime_binding(repository_root, environment)
        access_lease = issue_campaign_secret_access_lease(
            repository_root,
            required_scope,
            access_identity=f"live-qualification-jira:{os.getpid()}",
        )
    elif campaign_environment_declared:
        raise RuntimeError("campaign_jira_credential_must_use_a_bound_dpapi_envelope")
    token = SecretResolver(
        repository_root,
        environment,
        required_scope=required_scope,
        access_lease=access_lease,
    ).resolve(integrations.jira_api_token)
    return AtlassianJiraCloudAdapter(
        base_url=integrations.jira_base_url,
        user_email=integrations.jira_user_email,
        api_token=token,
    )


def _resolve_jira_remote_key(adapter: Any, repository_root: Path) -> str | None:
    task_path = repository_root / "jira" / "tasks" / f"{_LIVE_QUAL_JIRA_LOCAL_ID}.json"
    if task_path.is_file():
        payload = json.loads(task_path.read_text(encoding="utf-8"))
        remote_key = payload.get("remote_jira_key")
        if isinstance(remote_key, str) and remote_key.strip():
            return remote_key.strip()
        observed = payload.get("last_observed_remote_state")
        if isinstance(observed, dict):
            observed_key = observed.get("remote_key")
            if isinstance(observed_key, str) and observed_key.strip():
                return observed_key.strip()
    for issue in adapter.iter_issues("PP", page_size=100, fields=("summary", "description")):
        description = issue.description_text or ""
        if f"Local ID: {_LIVE_QUAL_JIRA_LOCAL_ID}" in description:
            return str(issue.remote_key)
    return None


def _probe_github_read(repository_slug: str) -> dict[str, Any]:
    if not _gh_auth_available():
        return {"credential_available": False}
    user_probe = _run_gh_json(["api", "user", "-q", ".login"])
    repo_probe = _run_gh_json(["repo", "view", repository_slug, "--json", "name,url"])
    read_ok = user_probe.get("ok") and repo_probe.get("ok")
    observations: dict[str, Any] = {"credential_available": True, "read_ok": read_ok}
    if user_probe.get("ok"):
        login = user_probe["payload"]
        observations["authenticated_login"] = login if isinstance(login, str) else str(login)
    if repo_probe.get("ok") and isinstance(repo_probe.get("payload"), dict):
        observations["repository_name"] = repo_probe["payload"].get("name")
        observations["repository_url"] = repo_probe["payload"].get("url")
    return observations


def _probe_jira_read(repository_root: Path) -> dict[str, Any]:
    try:
        adapter = _build_jira_adapter(repository_root)
    except ImportError as error:
        return {"credential_available": False, "reason": error.__class__.__name__}
    except Exception as error:
        return {"credential_available": False, "reason": error.__class__.__name__}

    try:
        adapter.discover_capabilities()
        project = adapter.get_project_metadata("PP")
        remote_key = _resolve_jira_remote_key(adapter, repository_root)
        return {
            "credential_available": True,
            "read_ok": True,
            "project_key": project.project_key,
            "project_name": project.name,
            "remote_key": remote_key,
        }
    except Exception as error:
        return {
            "credential_available": False,
            "reason": error.__class__.__name__,
        }
    finally:
        adapter.discard_secret_material()


def _probe_github_write_readback(repository_slug: str, token: str) -> dict[str, Any]:
    from project_pipeline.github_steward.adapter import GitHubRestAdapter
    from project_pipeline.github_steward.ports import GitHubWriteContext

    adapter = GitHubRestAdapter(token=token)
    context = GitHubWriteContext(
        actor_id="actor:pp384-live-qual",
        correlation_id="corr:pp384-github-write-readback",
        idempotency_key="pp384-live-qual-github-branch-probe",
        authorization_id="auth:pp384-live-qual-github",
    )
    branch_name = _GITHUB_PROBE_BRANCH
    try:
        metadata = adapter.get_repository(repository_slug)
        base_sha = next(
            (
                branch.sha
                for branch in adapter.iter_branches(repository_slug)
                if branch.name == metadata.default_branch
            ),
            None,
        )
        if not base_sha:
            return {
                "write_attempted": False,
                "write_readback_ok": False,
                "reason": "default_branch_sha_unavailable",
            }
        existing = {branch.name for branch in adapter.iter_branches(repository_slug)}
        if branch_name in existing:
            adapter.delete_branch(repository_slug, branch=branch_name, context=context)
        created = adapter.create_branch(
            repository_slug, branch=branch_name, sha=base_sha, context=context
        )
        observed_after_create = branch_name in {
            branch.name for branch in adapter.iter_branches(repository_slug)
        }
        adapter.delete_branch(repository_slug, branch=branch_name, context=context)
        observed_after_delete = _branch_absent_after_delete_readback(
            adapter,
            repository_slug=repository_slug,
            branch_name=branch_name,
        )
        readback_ok = (
            observed_after_create
            and observed_after_delete
            and created.name == branch_name
            and bool(created.sha)
        )
        return {
            "write_attempted": True,
            "write_readback_ok": readback_ok,
            "branch": branch_name,
            "base_branch": metadata.default_branch,
            "created_sha_prefix": created.sha[:12],
            "observed_after_create": observed_after_create,
            "observed_after_delete": observed_after_delete,
            "provider_id": adapter.provider_id,
        }
    except Exception as error:
        return {
            "write_attempted": True,
            "write_readback_ok": False,
            "reason": error.__class__.__name__,
        }
    finally:
        adapter.discard_secret_material()


def _branch_absent_after_delete_readback(
    adapter: Any,
    *,
    repository_slug: str,
    branch_name: str,
    attempts: int = _GITHUB_BRANCH_DELETE_READBACK_ATTEMPTS,
    delay_seconds: float = _GITHUB_BRANCH_DELETE_READBACK_DELAY_SECONDS,
    sleeper: Any = time.sleep,
) -> bool:
    """Confirm a successful GitHub branch deletion despite eventual read consistency."""

    for attempt in range(attempts):
        if branch_name not in {branch.name for branch in adapter.iter_branches(repository_slug)}:
            return True
        if attempt + 1 < attempts:
            sleeper(delay_seconds)
    return False


def _probe_jira_write_readback(repository_root: Path) -> dict[str, Any]:
    from project_pipeline.jira_steward.ports import JiraWriteContext

    try:
        adapter = _build_jira_adapter(repository_root)
    except Exception as error:
        return {
            "credential_available": False,
            "write_readback_ok": False,
            "reason": error.__class__.__name__,
        }

    try:
        remote_key = _resolve_jira_remote_key(adapter, repository_root)
        if not remote_key:
            return {
                "credential_available": True,
                "write_attempted": False,
                "write_readback_ok": False,
                "reason": "remote_key_unresolved",
            }
        context = JiraWriteContext(
            actor_id="actor:pp384-live-qual",
            correlation_id="corr:pp384-jira-write-readback",
            idempotency_key="pp384-live-qual-jira-comment-probe",
            authorization_id="auth:pp384-live-qual-jira",
        )
        probe_body = f"{_LIVE_QUAL_PROBE_MARKER}: governed live qualification probe"
        before = adapter.get_issue(remote_key)
        if before is None:
            return {
                "credential_available": True,
                "write_attempted": False,
                "write_readback_ok": False,
                "remote_key": remote_key,
                "reason": "issue_not_found",
            }
        if any(_LIVE_QUAL_PROBE_MARKER in (comment.body_text or "") for comment in before.comments):
            return {
                "credential_available": True,
                "write_attempted": False,
                "write_readback_ok": True,
                "remote_key": remote_key,
                "idempotent_reuse": True,
                "provider_id": adapter.provider_id,
            }
        comment = adapter.add_comment(remote_key=remote_key, body=probe_body, context=context)
        after = adapter.get_issue(remote_key)
        readback_ok = after is not None and any(
            comment.comment_id == observed.comment_id
            or _LIVE_QUAL_PROBE_MARKER in (observed.body_text or "")
            for observed in after.comments
        )
        return {
            "credential_available": True,
            "write_attempted": True,
            "write_readback_ok": readback_ok,
            "remote_key": remote_key,
            "comment_id": comment.comment_id,
            "provider_id": adapter.provider_id,
        }
    except Exception as error:
        return {
            "credential_available": True,
            "write_attempted": True,
            "write_readback_ok": False,
            "remote_key": remote_key,
            "reason": error.__class__.__name__,
        }
    finally:
        adapter.discard_secret_material()


def create_coordinator_jira_governance_receipt(
    *, repository_root: Path, coordinator_id: str = _PRIMARY_COORDINATOR_ID
) -> dict[str, Any]:
    """Perform the coordinator-owned live Jira check without exporting its credential."""

    head, tree = _git_identity(repository_root)
    if head is None or tree is None:
        raise RuntimeError("coordinator Jira receipt requires a valid Git candidate identity")
    jira_probe = _probe_jira_read(repository_root)
    jira_write_probe = _probe_jira_write_readback(repository_root)
    passed = bool(jira_probe.get("read_ok")) and bool(jira_write_probe.get("write_readback_ok"))
    receipt: dict[str, Any] = {
        "schema_version": _COORDINATOR_JIRA_RECEIPT_VERSION,
        "kind": _COORDINATOR_JIRA_RECEIPT_KIND,
        "status": "PASSED" if passed else "FAILED",
        "generated_at_utc": _utc_now(),
        "task_id": _LIVE_QUAL_JIRA_LOCAL_ID,
        "coordinator_id": coordinator_id,
        "candidate": {"sha": head, "tree": tree},
        "jira_probe": jira_probe,
        "jira_write_probe": jira_write_probe,
        "secret_value_observed": False,
    }
    receipt["receipt_sha256"] = _coordinator_jira_receipt_digest(receipt)
    return receipt


def _receipt_timestamp(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC).isoformat() if parsed.tzinfo is not None else None


def _coordinator_attestation_subject(
    path: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    state_field: str,
    timestamp_field: str,
    evidence_ref: str,
    policy: Any,
) -> dict[str, Any] | None:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or len(raw) != expected_bytes
        or hashlib.sha256(raw).hexdigest() != expected_sha256
        or payload.get("project_id") != policy.project_id
        or payload.get("provider_id") != policy.provider_id
        or payload.get("scope") != policy.scope
        or payload.get(state_field) is not True
    ):
        return None
    timestamp = _receipt_timestamp(payload.get(timestamp_field))
    if timestamp is None:
        return None
    return {
        "evidence_ref": evidence_ref,
        "sha256": expected_sha256,
        "byte_length": expected_bytes,
        "project_id": policy.project_id,
        "provider_id": policy.provider_id,
        "scope": policy.scope,
        state_field: True,
        timestamp_field: timestamp,
    }


def create_coordinator_attestation_receipt(
    *,
    repository_root: Path,
    attestation_source_root: Path,
    coordinator_id: str = _PRIMARY_COORDINATOR_ID,
) -> dict[str, Any]:
    """Attest private PP-379 records without copying their bytes to the CPU.

    The source records remain in the coordinator's private preservation store.
    Only policy-relevant identities and accepted immutable digests travel in the
    signed receipt.
    """

    head, tree = _git_identity(repository_root)
    if head is None or tree is None:
        raise RuntimeError("coordinator attestation receipt requires a valid Git candidate identity")
    policy = load_current_attestation_policy(repository_root)
    attestation = _coordinator_attestation_subject(
        attestation_source_root / PUBLIC_ATTESTATION_REF,
        expected_sha256=EXPECTED_PUBLIC_ATTESTATION_SHA256,
        expected_bytes=EXPECTED_PUBLIC_ATTESTATION_BYTES,
        state_field="approved",
        timestamp_field="approved_at_utc",
        evidence_ref=PUBLIC_ATTESTATION_REF,
        policy=policy,
    )
    qualification = _coordinator_attestation_subject(
        attestation_source_root / PUBLIC_QUALIFICATION_REF,
        expected_sha256=EXPECTED_PUBLIC_QUALIFICATION_SHA256,
        expected_bytes=EXPECTED_PUBLIC_QUALIFICATION_BYTES,
        state_field="qualified",
        timestamp_field="verified_at_utc",
        evidence_ref=PUBLIC_QUALIFICATION_REF,
        policy=policy,
    )
    receipt: dict[str, Any] = {
        "schema_version": _COORDINATOR_ATTESTATION_RECEIPT_VERSION,
        "kind": _COORDINATOR_ATTESTATION_RECEIPT_KIND,
        "status": "PASSED" if attestation and qualification else "FAILED",
        "generated_at_utc": _utc_now(),
        "task_id": _LIVE_QUAL_JIRA_LOCAL_ID,
        "coordinator_id": coordinator_id,
        "candidate": {"sha": head, "tree": tree},
        "attestation": attestation,
        "qualification": qualification,
        "secret_value_observed": False,
    }
    receipt["receipt_sha256"] = _coordinator_jira_receipt_digest(receipt)
    return receipt


def _coordinator_attestation_subject_matches(
    subject: object,
    *,
    expected_sha256: str,
    expected_bytes: int,
    state_field: str,
    timestamp_field: str,
    evidence_ref: str,
    policy: Any,
) -> bool:
    return (
        isinstance(subject, dict)
        and subject.get("evidence_ref") == evidence_ref
        and subject.get("sha256") == expected_sha256
        and subject.get("byte_length") == expected_bytes
        and subject.get("project_id") == policy.project_id
        and subject.get("provider_id") == policy.provider_id
        and subject.get("scope") == policy.scope
        and subject.get(state_field) is True
        and _receipt_timestamp(subject.get(timestamp_field)) is not None
    )


def _coordinator_attestation_receipt_probe(
    receipt_path: Path | None,
    signature_path: Path | None,
    *,
    repository_root: Path,
    expected_head: str | None,
    expected_tree: str | None,
) -> dict[str, Any]:
    """Validate a fresh, signed, candidate-bound relay for private PP-379 proof."""

    unavailable: dict[str, Any] = {"provided": receipt_path is not None, "valid": False}
    if receipt_path is None:
        unavailable["reason"] = "coordinator_attestation_receipt_not_provided"
        return unavailable
    if signature_path is None:
        unavailable["reason"] = "coordinator_attestation_signature_not_provided"
        return unavailable
    if expected_head is None or expected_tree is None:
        unavailable["reason"] = "candidate_identity_unavailable"
        return unavailable
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        unavailable["reason"] = "coordinator_attestation_receipt_unreadable"
        return unavailable
    if not isinstance(payload, dict):
        unavailable["reason"] = "coordinator_attestation_receipt_malformed"
        return unavailable
    receipt_sha256 = str(payload.get("receipt_sha256") or "").lower()
    if receipt_sha256 != _coordinator_jira_receipt_digest(payload):
        unavailable["reason"] = "coordinator_attestation_receipt_digest_mismatch"
        return unavailable
    generated = _receipt_timestamp(payload.get("generated_at_utc"))
    if generated is None:
        unavailable["reason"] = "coordinator_attestation_receipt_timestamp_invalid"
        return unavailable
    now = datetime.now(UTC)
    generated_at = datetime.fromisoformat(generated)
    if generated_at > now or now - generated_at > _COORDINATOR_JIRA_RECEIPT_MAX_AGE:
        unavailable["reason"] = "coordinator_attestation_receipt_stale"
        return unavailable
    candidate = payload.get("candidate")
    identity_matches = (
        isinstance(candidate, dict)
        and str(candidate.get("sha") or "").lower() == expected_head.lower()
        and str(candidate.get("tree") or "").lower() == expected_tree.lower()
    )
    policy = load_current_attestation_policy(repository_root)
    attestation_ok = _coordinator_attestation_subject_matches(
        payload.get("attestation"),
        expected_sha256=EXPECTED_PUBLIC_ATTESTATION_SHA256,
        expected_bytes=EXPECTED_PUBLIC_ATTESTATION_BYTES,
        state_field="approved",
        timestamp_field="approved_at_utc",
        evidence_ref=PUBLIC_ATTESTATION_REF,
        policy=policy,
    )
    qualification_ok = _coordinator_attestation_subject_matches(
        payload.get("qualification"),
        expected_sha256=EXPECTED_PUBLIC_QUALIFICATION_SHA256,
        expected_bytes=EXPECTED_PUBLIC_QUALIFICATION_BYTES,
        state_field="qualified",
        timestamp_field="verified_at_utc",
        evidence_ref=PUBLIC_QUALIFICATION_REF,
        policy=policy,
    )
    policy_matches = (
        payload.get("schema_version") == _COORDINATOR_ATTESTATION_RECEIPT_VERSION
        and payload.get("kind") == _COORDINATOR_ATTESTATION_RECEIPT_KIND
        and payload.get("status") == "PASSED"
        and payload.get("task_id") == _LIVE_QUAL_JIRA_LOCAL_ID
        and payload.get("coordinator_id") == _PRIMARY_COORDINATOR_ID
        and payload.get("secret_value_observed") is False
        and identity_matches
        and attestation_ok
        and qualification_ok
    )
    if not policy_matches:
        unavailable["reason"] = "coordinator_attestation_receipt_policy_mismatch"
        return unavailable
    allowed_signers = repository_root / _COORDINATOR_JIRA_ALLOWED_SIGNERS
    if not _verify_coordinator_signature(
        receipt_sha256=receipt_sha256,
        signature_path=signature_path,
        allowed_signers_path=allowed_signers,
        namespace=_COORDINATOR_ATTESTATION_SIGNATURE_NAMESPACE,
    ):
        unavailable["reason"] = "coordinator_attestation_signature_invalid"
        return unavailable
    return {
        "provided": True,
        "valid": True,
        "receipt_sha256": receipt_sha256,
        "generated_at_utc": generated,
        "signature_verified": True,
        "relay": "signed-private-attestation",
    }


def _run_windows_signature_verifier(
    command: list[str], *, message: bytes, comspec: str
) -> subprocess.CompletedProcess[bytes]:
    """Run OpenSSH verification through cmd redirection on Windows.

    Windows OpenSSH's ``ssh-keygen -Y verify`` can block indefinitely when it
    receives the signed message from a Python pipe.  A short-lived command file
    gives the program a real redirected file handle while retaining argument
    vector construction and deterministic cleanup.
    """

    with tempfile.TemporaryDirectory(prefix="project-pipeline-signature-") as temporary:
        temporary_root = Path(temporary)
        message_path = temporary_root / "message.txt"
        command_path = temporary_root / "verify.cmd"
        message_path.write_bytes(message)
        command_path.write_text(
            "@echo off\r\n"
            f"{subprocess.list2cmdline(command)} < {subprocess.list2cmdline([str(message_path)])}\r\n"
            "exit /b %ERRORLEVEL%\r\n",
            encoding="mbcs",
            newline="",
        )
        return subprocess.run(
            [comspec, "/d", "/c", str(command_path)],
            capture_output=True,
            timeout=30,
            check=False,
        )


def _verify_coordinator_signature(
    *,
    receipt_sha256: str,
    signature_path: Path,
    allowed_signers_path: Path,
    namespace: str,
) -> bool:
    """Verify one bounded coordinator receipt without moving a credential."""

    if (
        len(receipt_sha256) != 64
        or any(character not in "0123456789abcdef" for character in receipt_sha256)
        or not signature_path.is_file()
        or not allowed_signers_path.is_file()
    ):
        return False
    command = [
        "ssh-keygen",
        "-Y",
        "verify",
        "-f",
        str(allowed_signers_path),
        "-I",
        _PRIMARY_COORDINATOR_ID,
        "-n",
        namespace,
        "-s",
        str(signature_path),
    ]
    message = _coordinator_jira_receipt_message(receipt_sha256)
    try:
        if os.name == "nt":
            comspec = os.environ.get("COMSPEC")
            if not comspec:
                return False
            completed = _run_windows_signature_verifier(
                command,
                message=message,
                comspec=comspec,
            )
        else:
            completed = subprocess.run(
                command,
                input=message,
                capture_output=True,
                timeout=30,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _verify_coordinator_jira_signature(
    *, receipt_sha256: str, signature_path: Path, allowed_signers_path: Path
) -> bool:
    """Verify laptop-owned Jira evidence without moving a credential to the CPU worker."""

    return _verify_coordinator_signature(
        receipt_sha256=receipt_sha256,
        signature_path=signature_path,
        allowed_signers_path=allowed_signers_path,
        namespace=_COORDINATOR_JIRA_SIGNATURE_NAMESPACE,
    )


def _coordinator_jira_receipt_probe(
    receipt_path: Path | None,
    signature_path: Path | None,
    *,
    repository_root: Path,
    expected_head: str | None,
    expected_tree: str | None,
) -> dict[str, Any]:
    """Fail closed unless a fresh coordinator Jira receipt matches this candidate."""

    unavailable: dict[str, Any] = {
        "provided": receipt_path is not None,
        "valid": False,
        "write_readback_ok": False,
    }
    if receipt_path is None:
        unavailable["reason"] = "coordinator_jira_receipt_not_provided"
        return unavailable
    if signature_path is None:
        unavailable["reason"] = "coordinator_jira_signature_not_provided"
        return unavailable
    if expected_head is None or expected_tree is None:
        unavailable["reason"] = "candidate_identity_unavailable"
        return unavailable
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        unavailable["reason"] = "coordinator_jira_receipt_unreadable"
        return unavailable
    if not isinstance(payload, dict):
        unavailable["reason"] = "coordinator_jira_receipt_malformed"
        return unavailable
    receipt_sha256 = str(payload.get("receipt_sha256") or "").lower()
    if receipt_sha256 != _coordinator_jira_receipt_digest(payload):
        unavailable["reason"] = "coordinator_jira_receipt_digest_mismatch"
        return unavailable
    candidate = payload.get("candidate")
    jira_probe = payload.get("jira_probe")
    jira_write_probe = payload.get("jira_write_probe")
    try:
        generated = datetime.fromisoformat(
            str(payload.get("generated_at_utc") or "").replace("Z", "+00:00")
        )
    except ValueError:
        unavailable["reason"] = "coordinator_jira_receipt_timestamp_invalid"
        return unavailable
    if generated.tzinfo is None:
        unavailable["reason"] = "coordinator_jira_receipt_timestamp_unzoned"
        return unavailable
    generated = generated.astimezone(UTC)
    now = datetime.now(UTC)
    if generated > now or now - generated > _COORDINATOR_JIRA_RECEIPT_MAX_AGE:
        unavailable["reason"] = "coordinator_jira_receipt_stale"
        return unavailable
    identity_matches = (
        isinstance(candidate, dict)
        and str(candidate.get("sha") or "").lower() == expected_head.lower()
        and str(candidate.get("tree") or "").lower() == expected_tree.lower()
    )
    valid = (
        payload.get("schema_version") == _COORDINATOR_JIRA_RECEIPT_VERSION
        and payload.get("kind") == _COORDINATOR_JIRA_RECEIPT_KIND
        and payload.get("status") == "PASSED"
        and payload.get("task_id") == _LIVE_QUAL_JIRA_LOCAL_ID
        and payload.get("coordinator_id") == _PRIMARY_COORDINATOR_ID
        and payload.get("secret_value_observed") is False
        and identity_matches
        and isinstance(jira_probe, dict)
        and bool(jira_probe.get("read_ok"))
        and isinstance(jira_write_probe, dict)
        and bool(jira_write_probe.get("write_readback_ok"))
        and isinstance(jira_write_probe.get("remote_key"), str)
        and bool(str(jira_write_probe.get("remote_key")).strip())
    )
    if not valid:
        unavailable["reason"] = "coordinator_jira_receipt_policy_mismatch"
        return unavailable
    # mypy cannot retain narrowing through the aggregate validity predicate.
    # Repeat this already-required condition at the point of indexed access.
    if not isinstance(jira_write_probe, dict):
        unavailable["reason"] = "coordinator_jira_receipt_policy_mismatch"
        return unavailable
    allowed_signers = repository_root / _COORDINATOR_JIRA_ALLOWED_SIGNERS
    if not _verify_coordinator_jira_signature(
        receipt_sha256=receipt_sha256,
        signature_path=signature_path,
        allowed_signers_path=allowed_signers,
    ):
        unavailable["reason"] = "coordinator_jira_signature_invalid"
        return unavailable
    return {
        "provided": True,
        "valid": True,
        "read_ok": True,
        "write_readback_ok": True,
        "coordinator_id": _PRIMARY_COORDINATOR_ID,
        "remote_key": str(jira_write_probe["remote_key"]),
        "provider_id": str(jira_write_probe.get("provider_id") or "unknown"),
        "generated_at_utc": generated.isoformat(),
        "receipt_sha256": receipt_sha256,
        "signature_verified": True,
        "allowed_signers": str(_COORDINATOR_JIRA_ALLOWED_SIGNERS),
    }


def _qualify_windows_service(*, repository_root: Path, disposable_root: Path) -> StageResult:
    paths = build_paths(root=disposable_root)
    script = repository_root / "scripts" / "run_autonomy_runtime_service.py"
    service = AutonomyRuntimeWindowsService(paths)
    reasons: list[str] = []
    plan_valid = False
    plan_keys: list[str] = []
    if script.is_file():
        plan = plan_service_commands(paths, script)
        plan_keys = sorted(plan)
        plan_valid = all(key in plan for key in _SERVICE_PLAN_KEYS)
        if not plan_valid:
            reasons.append("service command plan incomplete")
    else:
        reasons.append("service launcher script missing")

    first_exit = service.run_foreground(max_seconds=0.1)
    first_health = service.health()
    checkpoint_path = paths.state_path.with_suffix(".checkpoint.json")
    checkpoint_status = None
    if checkpoint_path.is_file():
        checkpoint_status = json.loads(checkpoint_path.read_text(encoding="utf-8")).get("status")

    paths.pid_path.write_text("999999", encoding="utf-8")
    stale_health = service.health()
    recovery_exit = service.run_foreground(max_seconds=0.1)
    recovery_health = service.health()

    passed = (
        plan_valid
        and first_exit == 0
        and recovery_exit == 0
        and first_health["pid"] is None
        and recovery_health["pid"] is None
        and stale_health.get("stale_pid") is True
        and checkpoint_status == "STOPPED"
    )
    if first_exit != 0:
        reasons.append("initial foreground run failed")
    if recovery_exit != 0:
        reasons.append("recovery foreground run failed")
    if stale_health.get("stale_pid") is not True:
        reasons.append("stale pid was not detected before recovery")
    if checkpoint_status != "STOPPED":
        reasons.append("checkpoint did not record STOPPED status")

    return StageResult(
        stage_id="windows_service_foreground",
        outcome=StageOutcome.PASSED if passed else StageOutcome.FAILED,
        observations={
            "plan_valid": plan_valid,
            "plan_keys": plan_keys,
            "first_exit_code": first_exit,
            "recovery_exit_code": recovery_exit,
            "first_health": first_health,
            "recovery_health": recovery_health,
            "stale_pid_detected": stale_health.get("stale_pid"),
            "checkpoint_status": checkpoint_status,
        },
        reasons=tuple(reasons),
    )


def _qualify_command_center(*, disposable_root: Path) -> StageResult:
    supervisor_path = disposable_root / "state" / "live-qualification-sup.db"
    lane_path = disposable_root / "state" / "live-qualification-lanes.db"
    service_root = disposable_root / "state" / "live-qualification-service"
    service_root.mkdir(parents=True, exist_ok=True)
    service = AutonomyRuntimeWindowsService(build_paths(root=service_root))
    service.run_foreground(max_seconds=0.1)

    supervisor_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor = PersistentSupervisor(supervisor_path)
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000384",
        input_fingerprint="live-qualification",
        worker_id="local-qualifier",
        base_branch="main",
        worktree_path=str(disposable_root),
        lease_fence="live-qual-fence",
        idempotency_key="live-qual-cc",
        payload={"stage": "command_center_truth"},
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.record_result(
        operation_id=operation_id,
        worker_id="local-qualifier",
        output_fingerprint="live-qual-out",
        status="RESULT_OBSERVED",
        payload={"ok": True},
    )
    supervisor.mark_verified(operation_id, "verified-live-qual")
    supervisor.mark_integrated(operation_id, "b" * 40)
    supervisor.complete_operation(operation_id)
    supervisor.close()
    registry = LaneRegistry(lane_path)
    registry.close()
    snapshot = project_autonomy_runtime(
        supervisor_state=supervisor_path,
        lane_state=lane_path,
        service_root=service_root,
        ready_task_ids=["PP-TASK-000384", "PP-TASK-000385"],
        provider_status={"label": "local", "live_qualification": False, "source": "durable_state"},
    )
    restarted = project_autonomy_runtime(
        supervisor_state=supervisor_path,
        lane_state=lane_path,
        service_root=service_root,
        ready_task_ids=["PP-TASK-000384", "PP-TASK-000385"],
        provider_status={"label": "local", "live_qualification": False, "source": "durable_state"},
    )
    windows_service = snapshot["context_summary"].get("windows_service") or {}
    truth_ok = (
        snapshot["context_summary"]["source"] == "durable_state"
        and snapshot["context_summary"]["last_verified_sha"] == "b" * 40
        and snapshot["context_summary"]["next_eligible_task_id"] == "PP-TASK-000385"
        and snapshot["provider_summary"]["source"] == "durable_state"
        and windows_service.get("pid") is None
        and windows_service.get("checkpoint_exists") is True
        and restarted["context_summary"]["last_verified_sha"]
        == snapshot["context_summary"]["last_verified_sha"]
    )
    return StageResult(
        stage_id="command_center_truth",
        outcome=StageOutcome.PASSED if truth_ok else StageOutcome.FAILED,
        observations={
            "snapshot_id": snapshot.get("snapshot_id"),
            "context_summary": snapshot["context_summary"],
            "restart_last_verified_sha": restarted["context_summary"]["last_verified_sha"],
        },
        reasons=()
        if truth_ok
        else ("command center projection was not derived from durable state",),
    )


def _qualify_local_provider(disposable_root: Path) -> StageResult:
    runtime = AutonomyProviderRuntime(disposable_root / "state" / "live-qualification-provider.db")
    try:
        receipt = runtime.dispatch(
            provider=local_test_provider(),
            command=[sys.executable, "-c", "print('live-qual-local-provider')"],
            working_directory=disposable_root,
            task_id="PP-TASK-000384",
            worker_id="local-qualifier",
            model_or_tool="local-subprocess",
            budget=BudgetDecision(
                allowed=True, reason="live-qualification", decision_id="BUD-LQ-001"
            ),
            lease_fence="live-qual-fence",
            expected_fence="live-qual-fence",
            idempotency_key="live-qual-provider",
        )
    finally:
        runtime.close()
    passed = receipt["status"] == "SUCCEEDED" and receipt["live_qualification"] is True
    return StageResult(
        stage_id="local_provider_dispatch",
        outcome=StageOutcome.PASSED if passed else StageOutcome.FAILED,
        observations={
            "receipt_status": receipt["status"],
            "live_qualification": receipt["live_qualification"],
        },
        reasons=() if passed else ("local provider dispatch did not succeed",),
    )


def _qualify_github_jira_governance(
    repository_root: Path,
    *,
    candidate_head: str | None = None,
    candidate_tree: str | None = None,
    coordinator_jira_receipt: Path | None = None,
    coordinator_jira_signature: Path | None = None,
) -> StageResult:
    github_steward = repository_root / "src" / "project_pipeline" / "github_steward"
    jira_module = repository_root / "src" / "project_pipeline" / "jira_steward"
    present = github_steward.is_dir() and jira_module.is_dir()
    if not present:
        return StageResult(
            stage_id="github_jira_governance",
            outcome=StageOutcome.FAILED,
            observations={
                "github_steward": github_steward.exists(),
                "jira_steward": jira_module.exists(),
            },
            reasons=("governed adapter modules are missing",),
        )

    repository_slug = _DEFAULT_REPOSITORY_SLUG
    project_json = repository_root / "config" / "project.json"
    if project_json.is_file():
        repository_url = json.loads(project_json.read_text(encoding="utf-8")).get("repository", "")
        if isinstance(repository_url, str):
            parsed_slug = _github_repository_slug_from_url(repository_url)
            if parsed_slug is not None:
                repository_slug = parsed_slug

    coordinator_jira_probe = _coordinator_jira_receipt_probe(
        coordinator_jira_receipt,
        coordinator_jira_signature,
        repository_root=repository_root,
        expected_head=candidate_head,
        expected_tree=candidate_tree,
    )
    github_probe = _probe_github_read(repository_slug)
    local_jira_probe: dict[str, Any]
    local_jira_write_probe: dict[str, Any]
    if coordinator_jira_probe.get("valid"):
        local_jira_probe = {
            "not_attempted": True,
            "reason": "coordinator_owned_jira_receipt_verified",
        }
        local_jira_write_probe = dict(local_jira_probe)
        jira_probe = {
            "credential_available": True,
            "read_ok": True,
            "execution_owner": "coordinator-receipt",
            "remote_key": coordinator_jira_probe["remote_key"],
        }
        jira_write_probe = {
            "credential_available": True,
            "write_attempted": True,
            "write_readback_ok": True,
            "execution_owner": "coordinator-receipt",
            "remote_key": coordinator_jira_probe["remote_key"],
            "provider_id": coordinator_jira_probe["provider_id"],
            "receipt_sha256": coordinator_jira_probe["receipt_sha256"],
            "signature_verified": True,
        }
    else:
        local_jira_probe = _probe_jira_read(repository_root)
        local_jira_write_probe = _probe_jira_write_readback(repository_root)
        jira_probe = local_jira_probe
        jira_write_probe = local_jira_write_probe
    read_ok = bool(github_probe.get("read_ok")) or bool(jira_probe.get("read_ok"))

    github_write_probe: dict[str, Any] = {
        "write_attempted": False,
        "write_readback_ok": False,
        "reason": "github_token_unavailable",
    }
    token, token_source = _resolve_github_token(repository_root)
    if token:
        try:
            github_write_probe = _probe_github_write_readback(repository_slug, token)
            github_write_probe["token_source"] = token_source
        finally:
            token = ""

    github_ok = bool(github_write_probe.get("write_readback_ok"))
    jira_ok = bool(jira_write_probe.get("write_readback_ok"))
    write_readback_ok = github_ok and jira_ok

    if write_readback_ok:
        outcome = StageOutcome.PASSED
        reasons: tuple[str, ...] = ()
    else:
        outcome = StageOutcome.BLOCKED_EXTERNAL
        blocked_reasons: list[str] = []
        if not read_ok:
            blocked_reasons.append(
                "authorized GitHub/Jira live read requires scoped credentials before write/readback"
            )
        if not github_ok:
            blocked_reasons.append(
                "GitHub governed write/readback did not complete with receipt-bound readback"
            )
        if not jira_ok:
            blocked_reasons.append(
                "Jira governed write/readback did not complete with receipt-bound readback"
            )
        reasons = tuple(blocked_reasons)

    return StageResult(
        stage_id="github_jira_governance",
        outcome=outcome,
        observations={
            "adapters_present": True,
            "live_mutation_required": True,
            "qualification_class": "authorized_sandbox_or_live",
            "github_probe": github_probe,
            "jira_probe": jira_probe,
            "github_write_probe": github_write_probe,
            "jira_write_probe": jira_write_probe,
            "local_jira_probe": local_jira_probe,
            "local_jira_write_probe": local_jira_write_probe,
            "coordinator_jira_receipt": coordinator_jira_probe,
            "read_probe_ok": read_ok,
            "write_readback_ok": write_readback_ok,
        },
        reasons=reasons,
    )


def _qualify_cursor_cli_provider(
    repository_root: Path,
    disposable_root: Path,
    *,
    runner: Any | None = None,
    source_root: Path | None = None,
    durable_dir: Path | None = None,
    coordinator_attestation: dict[str, Any] | None = None,
) -> StageResult:
    report = qualify_cursor_cli_provider(
        repository_root=repository_root,
        disposable_root=disposable_root,
        source_root=source_root,
        durable_dir=durable_dir,
        runner=runner,
        coordinator_attestation=coordinator_attestation,
    )
    if runner is None and disposable_root.name == ".pp384_cursor_cli_runtime":
        with suppress(OSError):
            shutil.rmtree(disposable_root)
    outcome = StageOutcome(report["outcome"])
    return StageResult(
        stage_id="cursor_cli_provider_dispatch",
        outcome=outcome,
        observations=report,
        reasons=tuple(report.get("reasons") or ()),
    )


def _cursor_cli_disposable_root(repository_root: Path, live_root: Path, runner: Any | None) -> Path:
    # A real Cursor Agent must operate inside the governed checkout so shared
    # rules and shell hooks are active. The repository's .local directory is
    # intentionally .cursorignore-protected, so use an allowlisted tests path
    # and remove it immediately after qualification. Injected test runners keep
    # using the caller's disposable root.
    if runner is not None:
        return live_root
    return repository_root / "tests" / ".pp384_cursor_cli_runtime"


def _git_identity(repository_root: Path) -> tuple[str | None, str | None]:
    try:
        head = (
            subprocess.check_output(
                ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
                text=True,
                timeout=30,
            )
            .strip()
            .lower()
        )
        tree = (
            subprocess.check_output(
                ["git", "-C", str(repository_root), "rev-parse", "HEAD^{tree}"],
                text=True,
                timeout=30,
            )
            .strip()
            .lower()
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None
    if len(head) != 40 or len(tree) != 40:
        return None, None
    return head, tree


def _git_checkout_clean(repository_root: Path) -> bool:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "status", "--porcelain=v1"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and not completed.stdout.strip()


def run_live_qualification(
    *,
    repository_root: Path,
    disposable_root: Path | None = None,
    cursor_cli_runner: Any | None = None,
    attestation_source_root: Path | None = None,
    durable_dir: Path | None = None,
    coordinator_jira_receipt: Path | None = None,
    coordinator_jira_signature: Path | None = None,
    coordinator_attestation_receipt: Path | None = None,
    coordinator_attestation_signature: Path | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    default_root = repository_root / ".local" / "live_qualification_runtime"
    root = (disposable_root or default_root).resolve()
    if root.exists() and not remove_disposable_workspace(root):
        raise RuntimeError(f"disposable live qualification root is still locked: {root}")
    root.mkdir(parents=True, exist_ok=True)
    cursor_root = _cursor_cli_disposable_root(repository_root, root, cursor_cli_runner)
    if (
        cursor_cli_runner is None
        and cursor_root.exists()
        and cursor_root != root
        and not remove_disposable_workspace(cursor_root)
    ):
        raise RuntimeError(
            f"disposable cursor-cli qualification workspace is still locked: {cursor_root}"
        )
    candidate_head, candidate_tree = _git_identity(repository_root)
    candidate_clean_before = _git_checkout_clean(repository_root)
    coordinator_attestation = _coordinator_attestation_receipt_probe(
        coordinator_attestation_receipt,
        coordinator_attestation_signature,
        repository_root=repository_root,
        expected_head=candidate_head,
        expected_tree=candidate_tree,
    )
    stages: tuple[StageResult, ...] = (
        _qualify_windows_service(repository_root=repository_root, disposable_root=root),
        _qualify_command_center(disposable_root=root),
        _qualify_local_provider(root),
        _qualify_github_jira_governance(
            repository_root,
            candidate_head=candidate_head,
            candidate_tree=candidate_tree,
            coordinator_jira_receipt=coordinator_jira_receipt,
            coordinator_jira_signature=coordinator_jira_signature,
        ),
        _qualify_cursor_cli_provider(
            repository_root,
            _cursor_cli_disposable_root(repository_root, root, cursor_cli_runner),
            runner=cursor_cli_runner,
            source_root=attestation_source_root,
            durable_dir=durable_dir,
            coordinator_attestation=coordinator_attestation,
        ),
    )
    observed_head, observed_tree = _git_identity(repository_root)
    candidate_clean_after = _git_checkout_clean(repository_root)
    candidate_integrity_ok = (
        candidate_head is not None
        and candidate_tree is not None
        and candidate_clean_before
        and candidate_head == observed_head
        and candidate_tree == observed_tree
        and candidate_clean_after
    )
    stages += (
        StageResult(
            stage_id="candidate_checkout_integrity",
            outcome=StageOutcome.PASSED if candidate_integrity_ok else StageOutcome.FAILED,
            observations={
                "initial_head": candidate_head,
                "initial_tree": candidate_tree,
                "initial_checkout_clean": candidate_clean_before,
                "final_head": observed_head,
                "final_tree": observed_tree,
                "final_checkout_clean": candidate_clean_after,
            },
            reasons=()
            if candidate_integrity_ok
            else ("candidate identity changed, is unavailable, or checkout is not clean",),
        ),
    )
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "task_id": "PP-TASK-000384",
        "generated_at_utc": _utc_now(),
        "disposable_root": str(root),
        "stages": [stage.as_dict() for stage in stages],
    }
    body["bound_head"] = candidate_head
    body["bound_tree"] = candidate_tree
    recheck_path = root / "external_rechecks.json"
    store = AutonomousRecheckStore(recheck_path)
    cursor_stage = next(
        stage for stage in stages if stage.stage_id == "cursor_cli_provider_dispatch"
    )
    if cursor_stage.projected_outcome() is StageOutcome.BLOCKED_EXTERNAL:
        store.schedule(
            capability="cursor-cli",
            reason=" ".join(cursor_stage.reasons) or "cursor-cli executable unavailable",
            affected_lane_ids=("cursor-cli",),
            continuing_lane_ids=("windows-service", "command-center", "local-provider"),
        )
    body["autonomous_rechecks"] = store.snapshot()
    body["report_sha256"] = _digest(body)
    return body


def write_live_qualification_evidence(
    *,
    repository_root: Path,
    evidence_dir: Path | None = None,
    disposable_root: Path | None = None,
    cursor_cli_runner: Any | None = None,
    attestation_source_root: Path | None = None,
    durable_dir: Path | None = None,
    coordinator_jira_receipt: Path | None = None,
    coordinator_jira_signature: Path | None = None,
    coordinator_attestation_receipt: Path | None = None,
    coordinator_attestation_signature: Path | None = None,
) -> Path:
    report = run_live_qualification(
        repository_root=repository_root,
        disposable_root=disposable_root,
        cursor_cli_runner=cursor_cli_runner,
        attestation_source_root=attestation_source_root,
        durable_dir=durable_dir,
        coordinator_jira_receipt=coordinator_jira_receipt,
        coordinator_jira_signature=coordinator_jira_signature,
        coordinator_attestation_receipt=coordinator_attestation_receipt,
        coordinator_attestation_signature=coordinator_attestation_signature,
    )
    target = evidence_dir or (
        repository_root / ".local" / "evidence" / "autonomy_runtime" / "live_qualification"
    )
    target.mkdir(parents=True, exist_ok=True)
    output = target / "live_qualification_latest.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
