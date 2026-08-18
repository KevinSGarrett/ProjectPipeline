from __future__ import annotations

import hashlib
import json
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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _qualify_windows_service(root: Path) -> StageResult:
    paths = build_paths(root=root)
    service = AutonomyRuntimeWindowsService(paths)
    exit_code = service.run_foreground(max_seconds=0.1)
    health = service.health()
    restart_exit = service.run_foreground(max_seconds=0.1)
    restart_health = service.health()
    passed = exit_code == 0 and restart_exit == 0 and health["pid"] is None and restart_health["pid"] is None
    return StageResult(
        stage_id="windows_service_foreground",
        outcome=StageOutcome.PASSED if passed else StageOutcome.FAILED,
        observations={
            "first_exit_code": exit_code,
            "restart_exit_code": restart_exit,
            "first_health": health,
            "restart_health": restart_health,
        },
        reasons=() if passed else ("windows foreground lifecycle did not pass",),
    )


def _qualify_command_center(root: Path) -> StageResult:
    supervisor_path = root / "state" / "live-qualification-sup.db"
    lane_path = root / "state" / "live-qualification-lanes.db"
    service_root = root / "state" / "live-qualification-service"
    supervisor_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor = PersistentSupervisor(supervisor_path)
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000384",
        input_fingerprint="live-qualification",
        worker_id="local-qualifier",
        base_branch="main",
        worktree_path=str(root),
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
    truth_ok = (
        snapshot["context_summary"]["source"] == "durable_state"
        and snapshot["context_summary"]["last_verified_sha"] == "b" * 40
        and snapshot["provider_summary"]["source"] == "durable_state"
    )
    return StageResult(
        stage_id="command_center_truth",
        outcome=StageOutcome.PASSED if truth_ok else StageOutcome.FAILED,
        observations={"snapshot_id": snapshot.get("snapshot_id"), "context_summary": snapshot["context_summary"]},
        reasons=() if truth_ok else ("command center projection was not derived from durable state",),
    )


def _qualify_local_provider(root: Path) -> StageResult:
    runtime = AutonomyProviderRuntime(root / "state" / "live-qualification-provider.db")
    try:
        receipt = runtime.dispatch(
            provider=local_test_provider(),
            command=[sys.executable, "-c", "print('live-qual-local-provider')"],
            working_directory=root,
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
    return StageResult(
        stage_id="github_jira_governance",
        outcome=StageOutcome.BLOCKED_EXTERNAL,
        observations={
            "adapters_present": True,
            "live_mutation_required": True,
            "qualification_class": "authorized_sandbox_or_live",
        },
        reasons=(
            "authorized GitHub/Jira live read/write/readback requires scoped credentials and governed apply/readback; not attestation-blocked",
        ),
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
    root = (disposable_root or (repository_root / ".local" / "live_qualification_runtime")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stages = (
        _qualify_windows_service(root),
        _qualify_command_center(root),
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
