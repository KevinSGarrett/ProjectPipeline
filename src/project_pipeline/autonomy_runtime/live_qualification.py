from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.providers import (
    AutonomyProviderRuntime,
    BudgetDecision,
    local_test_provider,
)
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor
from project_pipeline.autonomy_runtime.windows_service import (
    AutonomyRuntimeWindowsService,
    build_paths,
    plan_service_commands,
)
from project_pipeline.command_center.autonomy import project_autonomy_runtime


class StageOutcome(str, Enum):
    PASSED = "PASSED"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    outcome: StageOutcome
    observations: dict[str, Any]
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "outcome": self.outcome.value,
            "observations": self.observations,
            "reasons": list(self.reasons),
        }


CURSOR_CLI_ATTESTATION_REF = "evidence/pp379_writer_attestation_evidence.json"
CURSOR_CLI_QUALIFICATION_REF = "evidence/pp379_writer_provider_qualification_evidence.json"
_SERVICE_PLAN_KEYS = ("install", "start", "stop", "restart", "uninstall", "status")
_DEFAULT_REPOSITORY_SLUG = "KevinSGarrett/ProjectPipeline"


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
        from project_pipeline.configuration.loader import load_runtime_configuration
        from project_pipeline.configuration.secrets import SecretResolver
        from project_pipeline.jira_steward.adapter import AtlassianJiraCloudAdapter
    except ImportError as error:
        return {"credential_available": False, "reason": error.__class__.__name__}

    try:
        configuration = load_runtime_configuration(repository_root)
        integrations = configuration.settings.integrations
        if not integrations.jira_base_url or not integrations.jira_user_email:
            return {"credential_available": False, "reason": "jira_integration_not_configured"}
        if integrations.jira_api_token is None:
            return {"credential_available": False, "reason": "jira_api_token_unconfigured"}
        token = SecretResolver(repository_root).resolve(integrations.jira_api_token)
        adapter = AtlassianJiraCloudAdapter(
            base_url=integrations.jira_base_url,
            user_email=integrations.jira_user_email,
            api_token=token,
        )
        adapter.discover_capabilities()
        project = adapter.get_project_metadata("PP")
        return {
            "credential_available": True,
            "read_ok": True,
            "project_key": project.project_key,
            "project_name": project.name,
        }
    except Exception as error:
        return {
            "credential_available": False,
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
        reasons=() if truth_ok else ("command center projection was not derived from durable state",),
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
            budget=BudgetDecision(allowed=True, reason="live-qualification", decision_id="BUD-LQ-001"),
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
        observations={"receipt_status": receipt["status"], "live_qualification": receipt["live_qualification"]},
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
            observations={"github_steward": github_steward.exists(), "jira_steward": jira_module.exists()},
            reasons=("governed adapter modules are missing",),
        )

    repository_slug = _DEFAULT_REPOSITORY_SLUG
    project_json = repository_root / "config" / "project.json"
    if project_json.is_file():
        repository_url = json.loads(project_json.read_text(encoding="utf-8")).get("repository", "")
        if isinstance(repository_url, str) and "github.com/" in repository_url:
            repository_slug = repository_url.rstrip("/").split("github.com/", 1)[-1]

    github_probe = _probe_github_read(repository_slug)
    jira_probe = _probe_jira_read(repository_root)
    read_ok = bool(github_probe.get("read_ok")) or bool(jira_probe.get("read_ok"))
    reasons = [
        "governed write/readback qualification is out of scope for attestation-free stage-C; read probes are honest",
    ]
    if not read_ok:
        reasons.insert(
            0,
            "authorized GitHub/Jira live read requires scoped credentials; write/readback not attempted",
        )
    return StageResult(
        stage_id="github_jira_governance",
        outcome=StageOutcome.BLOCKED_EXTERNAL,
        observations={
            "adapters_present": True,
            "live_mutation_required": True,
            "qualification_class": "authorized_sandbox_or_live",
            "github_probe": github_probe,
            "jira_probe": jira_probe,
            "read_probe_ok": read_ok,
        },
        reasons=tuple(reasons),
    )


def _qualify_cursor_cli_provider(repository_root: Path) -> StageResult:
    attestation_path = repository_root / CURSOR_CLI_ATTESTATION_REF
    qualification_path = repository_root / CURSOR_CLI_QUALIFICATION_REF
    missing = []
    if not attestation_path.is_file():
        missing.append(CURSOR_CLI_ATTESTATION_REF)
    if not qualification_path.is_file():
        missing.append(CURSOR_CLI_QUALIFICATION_REF)
    if missing:
        return StageResult(
            stage_id="cursor_cli_provider_dispatch",
            outcome=StageOutcome.HUMAN_REQUIRED,
            observations={
                "provider_id": "provider:cursor-cli",
                "missing_evidence": missing,
                "attestation_reference": CURSOR_CLI_ATTESTATION_REF,
                "qualification_reference": CURSOR_CLI_QUALIFICATION_REF,
            },
            reasons=tuple(f"missing evidence artifact: {item}" for item in missing),
        )
    return StageResult(
        stage_id="cursor_cli_provider_dispatch",
        outcome=StageOutcome.BLOCKED_EXTERNAL,
        observations={"provider_id": "provider:cursor-cli", "evidence_present": True},
        reasons=("evidence artifacts exist; live dispatch qualification still requires operator session",),
    )


def run_live_qualification(
    *,
    repository_root: Path,
    disposable_root: Path | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    root = (disposable_root or (repository_root / ".local" / "live_qualification_runtime")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stages = (
        _qualify_windows_service(repository_root=repository_root, disposable_root=root),
        _qualify_command_center(disposable_root=root),
        _qualify_local_provider(root),
        _qualify_github_jira_governance(repository_root),
        _qualify_cursor_cli_provider(repository_root),
    )
    body = {
        "schema_version": "1.0.0",
        "task_id": "PP-TASK-000384",
        "generated_at_utc": _utc_now(),
        "disposable_root": str(root),
        "stages": [stage.as_dict() for stage in stages],
    }
    body["report_sha256"] = _digest(body)
    return body


def write_live_qualification_evidence(
    *,
    repository_root: Path,
    evidence_dir: Path | None = None,
    disposable_root: Path | None = None,
) -> Path:
    report = run_live_qualification(repository_root=repository_root, disposable_root=disposable_root)
    target = evidence_dir or (repository_root / "evidence" / "autonomy_runtime" / "live_qualification")
    target.mkdir(parents=True, exist_ok=True)
    output = target / "live_qualification_latest.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
