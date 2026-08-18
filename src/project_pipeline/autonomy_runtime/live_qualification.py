from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    qualify_cursor_cli_provider,
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
    import os

    from project_pipeline.configuration.loader import parse_env_file

    merged = dict(os.environ)
    merged.update(parse_env_file(repository_root / ".env"))
    project_json = repository_root / "config" / "project.json"
    if project_json.is_file():
        target_root = json.loads(project_json.read_text(encoding="utf-8")).get("target_local_root")
        if isinstance(target_root, str) and target_root.strip():
            canonical_env = Path(target_root).expanduser().resolve() / ".env"
            if canonical_env.is_file():
                merged.update(parse_env_file(canonical_env))
    return merged


def _resolve_github_token(repository_root: Path) -> tuple[str | None, str]:
    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed is not None and completed.returncode == 0:
        token = completed.stdout.strip()
        if token:
            return token, "gh-auth"
    try:
        from project_pipeline.configuration.loader import load_runtime_configuration
        from project_pipeline.configuration.secrets import SecretResolver

        configuration = load_runtime_configuration(
            repository_root, environment=_credential_environment(repository_root)
        )
        token_ref = configuration.settings.integrations.github_token
        if token_ref is not None:
            token = SecretResolver(
                repository_root, _credential_environment(repository_root)
            ).resolve(token_ref)
            if token.strip():
                return token, "config"
    except Exception:
        return None, "none"
    return None, "none"


def _build_jira_adapter(repository_root: Path) -> Any:
    from project_pipeline.configuration.loader import load_runtime_configuration
    from project_pipeline.configuration.secrets import SecretResolver
    from project_pipeline.jira_steward.adapter import AtlassianJiraCloudAdapter

    configuration = load_runtime_configuration(
        repository_root, environment=_credential_environment(repository_root)
    )
    integrations = configuration.settings.integrations
    if not integrations.jira_base_url or not integrations.jira_user_email:
        raise RuntimeError("jira_integration_not_configured")
    if integrations.jira_api_token is None:
        raise RuntimeError("jira_api_token_unconfigured")
    token = SecretResolver(repository_root, _credential_environment(repository_root)).resolve(
        integrations.jira_api_token
    )
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
        observed_after_delete = branch_name not in {
            branch.name for branch in adapter.iter_branches(repository_slug)
        }
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
    try:
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


def _qualify_github_jira_governance(repository_root: Path) -> StageResult:
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

    github_probe = _probe_github_read(repository_slug)
    jira_probe = _probe_jira_read(repository_root)
    read_ok = bool(github_probe.get("read_ok")) or bool(jira_probe.get("read_ok"))

    github_write_probe: dict[str, Any] = {
        "write_attempted": False,
        "write_readback_ok": False,
        "reason": "github_token_unavailable",
    }
    token, token_source = _resolve_github_token(repository_root)
    if token:
        github_write_probe = _probe_github_write_readback(repository_slug, token)
        github_write_probe["token_source"] = token_source

    jira_write_probe = _probe_jira_write_readback(repository_root)
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
) -> StageResult:
    report = qualify_cursor_cli_provider(
        repository_root=repository_root,
        disposable_root=disposable_root,
        source_root=source_root,
        durable_dir=durable_dir,
        runner=runner,
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


def run_live_qualification(
    *,
    repository_root: Path,
    disposable_root: Path | None = None,
    cursor_cli_runner: Any | None = None,
    attestation_source_root: Path | None = None,
    durable_dir: Path | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    default_root = repository_root / ".local" / "live_qualification_runtime"
    root = (disposable_root or default_root).resolve()
    if disposable_root is None and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    stages = (
        _qualify_windows_service(repository_root=repository_root, disposable_root=root),
        _qualify_command_center(disposable_root=root),
        _qualify_local_provider(root),
        _qualify_github_jira_governance(repository_root),
        _qualify_cursor_cli_provider(
            repository_root,
            _cursor_cli_disposable_root(repository_root, root, cursor_cli_runner),
            runner=cursor_cli_runner,
            source_root=attestation_source_root,
            durable_dir=durable_dir,
        ),
    )
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "task_id": "PP-TASK-000384",
        "generated_at_utc": _utc_now(),
        "disposable_root": str(root),
        "stages": [stage.as_dict() for stage in stages],
    }
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
) -> Path:
    report = run_live_qualification(
        repository_root=repository_root,
        disposable_root=disposable_root,
        cursor_cli_runner=cursor_cli_runner,
        attestation_source_root=attestation_source_root,
        durable_dir=durable_dir,
    )
    target = evidence_dir or (
        repository_root / "evidence" / "autonomy_runtime" / "live_qualification"
    )
    target.mkdir(parents=True, exist_ok=True)
    output = target / "live_qualification_latest.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
