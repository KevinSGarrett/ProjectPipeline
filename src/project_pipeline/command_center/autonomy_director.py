"""Persistent Autonomy Director above the Control Kernel.

Director Chat is not this component. Raw chat text cannot mutate director state
or select work. Canonical transitions remain with Project Control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.command_center.director_runtime import (
    DirectorRuntime,
    DirectorRuntimeError,
    default_director_claims,
    qualify_local_provider,
)
from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.control.kernel import ProjectControlKernel
from project_pipeline.control.persistence import ControlStore
from project_pipeline.domain.control import (
    BuildSequence,
    CompletionProjection,
    CompletionProjectionState,
    ControlSnapshot,
    CriticalPathAnalysis,
    EligibilityState,
    ReadinessState,
    ScopeReconciliationReport,
    SequenceItem,
    SequenceScore,
    TaskEligibility,
    TaskReadiness,
    control_identifier,
)
from project_pipeline.domain.scheduler import ResourceClaim
from project_pipeline.persistence import SQLiteStateStore
from project_pipeline.services.state import CoreStateService


class AutonomyDirectorError(RuntimeError):
    """Fail-closed persistent director error."""


def default_state_path(root: Path) -> Path:
    return root.resolve() / ".local" / "state" / "autonomy_director" / "director_state.json"


def repository_identity(root: Path) -> tuple[str | None, str | None]:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD", "HEAD^{tree}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None, None
    lines = [line.strip().lower() for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) < 2 or len(lines[0]) != 40 or len(lines[1]) != 40:
        return None, None
    return lines[0], lines[1]


def evaluate_live_control(
    root: Path,
    *,
    database_path: Path | None = None,
) -> ControlSnapshot:
    """Construct and persist a Control snapshot from the live kernel and repository identity."""

    root = root.resolve()
    configuration = load_runtime_configuration(root)
    project_id = configuration.settings.project_id
    database = (
        Path(database_path)
        if database_path is not None
        else configuration.settings.database_path(root)
    )
    with SQLiteStateStore(database, root) as store:
        store.initialize()
        service = CoreStateService(store, root)
        if store.get_project_manifest(project_id) is None:
            service.initialize_from_repository(
                actor_id="actor:live-command-center",
                correlation_id="corr:live-control-snapshot",
            )
        snapshot = ProjectControlKernel(root, store, project_id).evaluate()
    head_sha, tree_sha = repository_identity(root)
    bound = snapshot
    if head_sha and tree_sha:
        fingerprint = hashlib.sha256(
            f"{snapshot.snapshot_fingerprint}:{head_sha}:{tree_sha}".encode("ascii")
        ).hexdigest()
        bound = snapshot.model_copy(
            update={
                "snapshot_fingerprint": fingerprint,
                "snapshot_id": control_identifier("CTRL", project_id, fingerprint),
            }
        )
    with ControlStore(database, root) as control_store:
        control_store.save_snapshot(bound)
    return bound


@dataclass(frozen=True, slots=True)
class DirectorDecision:
    decision_id: str
    selected_task_id: str | None
    citations: tuple[str, ...]
    rationale: str
    control_snapshot_id: str
    decided_at_utc: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "selected_task_id": self.selected_task_id,
            "citations": list(self.citations),
            "rationale": self.rationale,
            "control_snapshot_id": self.control_snapshot_id,
            "decided_at_utc": self.decided_at_utc.isoformat(),
        }


class PersistentAutonomyDirector:
    """Persist director decisions across process restart without chat mutation."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path.resolve()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {
                "schema_version": "1.1.0",
                "revision": 0,
                "decisions": [],
                "strategies": [],
                "executions": [],
                "recoveries": [],
                "last_selected_task_id": None,
                "last_control_fingerprint": None,
                "last_decision_id": None,
                "fence_token": None,
                "recovered": False,
            }
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AutonomyDirectorError("director state is not an object")
        return payload

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.state_path)

    def reject_raw_chat_mutation(self, text: str) -> None:
        raise AutonomyDirectorError(
            "raw chat cannot mutate Persistent Autonomy Director state or select work"
        )

    def _eligible_ready(self, control: ControlSnapshot) -> tuple[str, ...]:
        ready_ids = {item.task_id for item in control.readiness if item.ready}
        eligible_ids = {item.task_id for item in control.eligibility if item.eligible}
        denied = []
        selected: list[str] = []
        for item in control.sequence.ordered_ready_work:
            if item.task_id not in ready_ids:
                denied.append(f"not-ready:{item.task_id}")
                continue
            if item.task_id not in eligible_ids:
                denied.append(f"ineligible:{item.task_id}")
                continue
            if item.readiness != ReadinessState.READY:
                denied.append(f"sequence-not-ready:{item.task_id}")
                continue
            selected.append(item.task_id)
        self._state["last_rejection_codes"] = denied
        return tuple(selected)

    def select_next_work(
        self,
        control: ControlSnapshot,
        *,
        now: datetime | None = None,
        expected_fingerprint: str | None = None,
        requested_task_id: str | None = None,
    ) -> DirectorDecision:
        now = now or datetime.now(UTC)
        if expected_fingerprint and expected_fingerprint != control.snapshot_fingerprint:
            raise AutonomyDirectorError(
                "stale control fingerprint; refusing changed-head continuation"
            )
        ready = self._eligible_ready(control)
        if requested_task_id is not None and requested_task_id not in ready:
            raise AutonomyDirectorError(
                f"rejected selection {requested_task_id}: not Control-ready and eligible"
            )
        selected = (
            requested_task_id if requested_task_id is not None else (ready[0] if ready else None)
        )
        citations = (
            f"control:{control.snapshot_id}",
            f"fingerprint:{control.snapshot_fingerprint}",
            *(f"ready:{task_id}" for task_id in ready[:8]),
        )
        if selected is None:
            rationale = "Control Kernel reports no ready work; director does not invent a lane."
        else:
            rationale = (
                "Director selected the highest-ranked Control-ready lane without replacing "
                "canonical transition authority."
            )
        revision = int(self._state.get("revision") or 0) + 1
        decision = DirectorDecision(
            decision_id=f"DIRDEC-{revision:08d}",
            selected_task_id=selected,
            citations=citations,
            rationale=rationale,
            control_snapshot_id=control.snapshot_id,
            decided_at_utc=now,
        )
        decisions = list(self._state.get("decisions") or [])
        decisions.append(
            {
                "decision_id": decision.decision_id,
                "selected_task_id": decision.selected_task_id,
                "citations": list(decision.citations),
                "rationale": decision.rationale,
                "control_snapshot_id": decision.control_snapshot_id,
                "control_fingerprint": control.snapshot_fingerprint,
                "decided_at_utc": decision.decided_at_utc.isoformat(),
            }
        )
        self._state.update(
            {
                "schema_version": "1.1.0",
                "revision": revision,
                "decisions": decisions[-50:],
                "last_selected_task_id": selected,
                "last_control_fingerprint": control.snapshot_fingerprint,
                "last_decision_id": decision.decision_id,
                "readmission_required": False,
                "last_observation": {
                    "snapshot_id": control.snapshot_id,
                    "fingerprint": control.snapshot_fingerprint,
                    "citations": list(citations),
                },
                "recovered": False,
                "updated_at_utc": now.isoformat(),
            }
        )
        self._save()
        return decision

    def record_strategy(
        self,
        *,
        goal: str,
        plan_steps: tuple[str, ...],
        alternatives: tuple[str, ...],
        assumptions: tuple[str, ...],
        ambiguity: str,
        risk: str,
        resource_claims: tuple[str, ...],
        evidence_citations: tuple[str, ...],
        acceptance_checks: tuple[str, ...],
        rollback_boundary: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        if not self._state.get("last_decision_id"):
            raise AutonomyDirectorError("strategy requires an accepted Control-bound decision")
        if ambiguity == "HIGH_IMPACT_UNRESOLVED":
            record: dict[str, Any] = {
                "strategy_id": f"DIRSTR-{int(self._state.get('revision') or 0):08d}",
                "status": "ROUTED_TO_NEXT_ELIGIBLE",
                "goal": goal,
                "ambiguity": ambiguity,
                "risk": risk,
                "recorded_at_utc": now.isoformat(),
            }
            strategies = list(self._state.get("strategies") or [])
            strategies.append(record)
            self._state["strategies"] = strategies[-50:]
            self._save()
            return record
        accepted: dict[str, Any] = {
            "strategy_id": f"DIRSTR-{int(self._state.get('revision') or 0):08d}",
            "status": "ACCEPTED",
            "decision_id": self._state.get("last_decision_id"),
            "goal": goal,
            "plan_steps": list(plan_steps),
            "alternatives": list(alternatives),
            "assumptions": list(assumptions),
            "ambiguity": ambiguity,
            "risk": risk,
            "resource_claims": list(resource_claims),
            "evidence_citations": list(evidence_citations),
            "acceptance_checks": list(acceptance_checks),
            "rollback_boundary": rollback_boundary,
            "idempotency_key": hashlib.sha256(
                f"{self._state.get('last_decision_id')}:{goal}:{rollback_boundary}".encode()
            ).hexdigest(),
            "recorded_at_utc": now.isoformat(),
        }
        strategies = list(self._state.get("strategies") or [])
        if any(item.get("idempotency_key") == accepted["idempotency_key"] for item in strategies):
            raise AutonomyDirectorError(
                "conflicting strategy replay for the same decision boundary"
            )
        strategies.append(accepted)
        self._state["strategies"] = strategies[-50:]
        self._state["last_strategy_id"] = accepted["strategy_id"]
        self._save()
        return accepted

    def admit_current_selection(self, control: ControlSnapshot) -> str:
        selected = self._state.get("last_selected_task_id")
        fingerprint = self._state.get("last_control_fingerprint")
        if not selected or not self._state.get("last_decision_id"):
            raise AutonomyDirectorError(
                "execution coordination requires a selected Control-ready unit"
            )
        if self._state.get("readmission_required"):
            raise AutonomyDirectorError(
                "restart recovery requires Control readmission before dispatch"
            )
        if fingerprint and fingerprint != control.snapshot_fingerprint:
            raise AutonomyDirectorError(
                "stale control fingerprint; refusing changed-head continuation"
            )
        ready = self._eligible_ready(control)
        if selected not in ready:
            raise AutonomyDirectorError(
                f"rejected selection {selected}: not Control-ready and eligible"
            )
        return str(selected)

    def coordinate_execution(
        self,
        *,
        provider: str,
        root: Path,
        database: Path,
        control: ControlSnapshot,
        blocked_lanes: tuple[str, ...] = (),
        claims: tuple[ResourceClaim, ...] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        selected = self.admit_current_selection(control)
        decision_id = str(self._state.get("last_decision_id") or "")
        if not decision_id:
            raise AutonomyDirectorError("execution coordination requires a persisted decision id")
        fingerprint = str(self._state.get("last_control_fingerprint") or "")
        if self._state.get("fence_token"):
            raise AutonomyDirectorError("stale fence still held; recover before dispatch")
        for lane in blocked_lanes:
            if lane == selected:
                raise AutonomyDirectorError("selected lane cannot be both blocked and dispatched")
        try:
            admitted = qualify_local_provider(provider)
        except DirectorRuntimeError as exc:
            raise AutonomyDirectorError(str(exc)) from exc
        runtime = DirectorRuntime(root, database)
        acquired = runtime.acquire(
            task_id=selected,
            holder_id=f"director:{decision_id}",
            claims=claims or default_director_claims(selected),
            now=now,
        )
        if not acquired["acquired"]:
            record = {
                "execution_id": f"DIREX-{int(self._state.get('revision') or 0):08d}",
                "decision_id": decision_id,
                "selected_task_id": selected,
                "status": "BLOCKED",
                "blocked_lanes": [selected, *blocked_lanes],
                "continuing_lanes": [lane for lane in blocked_lanes if lane != selected],
                "scheduler_reasons": acquired["reasons"],
                "external_mutation": "GOVERNED_ADAPTERS_ONLY",
                "recorded_at_utc": now.isoformat(),
            }
            executions = list(self._state.get("executions") or [])
            executions.append(record)
            self._state["executions"] = executions[-50:]
            self._state["last_execution_id"] = record["execution_id"]
            self._save()
            return record
        pack = runtime.compile_context(
            task_id=selected,
            decision_id=decision_id,
            control_fingerprint=fingerprint or "unbound",
            now=now,
        )
        fence = hashlib.sha256(
            f"{decision_id}:{selected}:{acquired['leases'][0]['lease_id']}".encode()
        ).hexdigest()
        operation_id = runtime.persist_operation(
            task_id=selected,
            decision_id=decision_id,
            fence_token=fence,
            context_identity=pack["pack_id"],
            provider=admitted,
            input_fingerprint=hashlib.sha256(
                f"{decision_id}:{pack['pack_id']}".encode()
            ).hexdigest(),
        )
        record = {
            "execution_id": f"DIREX-{int(self._state.get('revision') or 0):08d}",
            "decision_id": decision_id,
            "selected_task_id": selected,
            "fence_token": fence,
            "scheduler_claim": acquired["leases"][0]["lease_id"],
            "leases": acquired["leases"],
            "context_identity": pack["pack_id"],
            "delegation_id": pack["delegation_id"],
            "operation_id": operation_id,
            "provider": admitted,
            "status": "DISPATCHED",
            "blocked_lanes": list(blocked_lanes),
            "continuing_lanes": [selected],
            "external_mutation": "GOVERNED_ADAPTERS_ONLY",
            "recorded_at_utc": now.isoformat(),
        }
        executions = list(self._state.get("executions") or [])
        executions.append(record)
        self._state["executions"] = executions[-50:]
        self._state["fence_token"] = fence
        self._state["last_execution_id"] = record["execution_id"]
        self._state["last_provider"] = admitted
        self._state["last_context_identity"] = pack["pack_id"]
        self._state["last_operation_id"] = operation_id
        self._state["active_leases"] = acquired["leases"]
        self._save()
        return record

    def recover_boundary(
        self,
        *,
        stage: str,
        external_readback: str,
        retry_authorized: bool,
        root: Path | None = None,
        database: Path | None = None,
        expected_head_sha: str | None = None,
        expected_tree_sha: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        allowed = {
            "intent_persisted",
            "lease_acquired",
            "dispatched",
            "partial_result",
            "verified",
            "unknown_external_write",
        }
        if stage not in allowed:
            raise AutonomyDirectorError(f"unsupported recovery boundary: {stage}")
        if stage == "unknown_external_write" and external_readback == "UNKNOWN":
            raise AutonomyDirectorError(
                "unknown GitHub/Jira outcome must be read back before retry"
            )
        observed_head, observed_tree = (
            repository_identity(root) if root is not None else (None, None)
        )
        changed_head = bool(
            expected_head_sha and observed_head and expected_head_sha.lower() != observed_head
        ) or bool(
            expected_tree_sha and observed_tree and expected_tree_sha.lower() != observed_tree
        )
        if changed_head:
            raise AutonomyDirectorError(
                "changed HEAD/tree; refusing recovery continuation without a new Control selection"
            )
        retryable = external_readback in {"ABSENT", "FAILED", "NOT_APPLIED"}
        if root is not None and database is not None:
            runtime = DirectorRuntime(root, database)
            leases = list(self._state.get("active_leases") or [])
            runtime.release(leases, now=now)
            operation_id = self._state.get("last_operation_id")
            if stage == "unknown_external_write" and operation_id:
                runtime.recover_unknown(
                    str(operation_id),
                    applied=external_readback == "APPLIED",
                )
        record = {
            "recovery_id": f"DIRREC-{int(self._state.get('revision') or 0):08d}",
            "stage": stage,
            "fence_token": self._state.get("fence_token"),
            "external_readback": external_readback,
            "retry_authorized": bool(retry_authorized and retryable),
            "double_merge_rejected": external_readback == "APPLIED",
            "changed_head_rejected": changed_head,
            "observed_head_sha": observed_head,
            "observed_tree_sha": observed_tree,
            "recorded_at_utc": now.isoformat(),
        }
        recoveries = list(self._state.get("recoveries") or [])
        recoveries.append(record)
        self._state["recoveries"] = recoveries[-50:]
        self._state["fence_token"] = None
        self._state["active_leases"] = []
        self._state["last_recovery_id"] = record["recovery_id"]
        self._state["recovered"] = True
        self._save()
        return record

    def recover(self) -> dict[str, Any]:
        self._state = self._load()
        self._state["recovered"] = True
        self._state["readmission_required"] = True
        self._save()
        return {
            "revision": int(self._state.get("revision") or 0),
            "last_selected_task_id": self._state.get("last_selected_task_id"),
            "decision_count": len(self._state.get("decisions") or []),
            "recovered": True,
            "readmission_required": True,
        }

    def projection(self) -> dict[str, Any]:
        strategies = list(self._state.get("strategies") or [])
        executions = list(self._state.get("executions") or [])
        recoveries = list(self._state.get("recoveries") or [])
        latest_strategy = strategies[-1] if strategies else None
        latest_execution = executions[-1] if executions else None
        return {
            "kind": "persistent_autonomy_director",
            "authoritative_for_transitions": False,
            "canonical_authority": "PROJECT_CONTROL_KERNEL",
            "revision": int(self._state.get("revision") or 0),
            "last_selected_task_id": self._state.get("last_selected_task_id"),
            "last_decision_id": self._state.get("last_decision_id"),
            "control_fingerprint": self._state.get("last_control_fingerprint"),
            "strategy_id": self._state.get("last_strategy_id"),
            "goal": None if latest_strategy is None else latest_strategy.get("goal"),
            "plan_steps": [] if latest_strategy is None else latest_strategy.get("plan_steps", []),
            "lease_fence": self._state.get("fence_token"),
            "context_identity": self._state.get("last_context_identity"),
            "worker_provider": self._state.get("last_provider"),
            "execution_status": None
            if latest_execution is None
            else latest_execution.get("status"),
            "blocked_lanes": []
            if latest_execution is None
            else latest_execution.get("blocked_lanes", []),
            "continuing_lanes": (
                [] if latest_execution is None else latest_execution.get("continuing_lanes", [])
            ),
            "recovery_state": self._state.get("last_recovery_id"),
            "decision_count": len(self._state.get("decisions") or []),
            "strategy_count": len(strategies),
            "execution_count": len(executions),
            "recovery_count": len(recoveries),
            "recovered": bool(self._state.get("recovered")),
            "readmission_required": bool(self._state.get("readmission_required")),
            "chat_mutation": False,
            "typed_controls": (
                "select",
                "record_strategy",
                "coordinate_execution",
                "recover_boundary",
            ),
        }


def control_snapshot_for_selection(task_ids: tuple[str, ...]) -> ControlSnapshot:
    """Build a Control-shaped snapshot for director selection without inventing work."""

    now = datetime.now(UTC)
    items = tuple(
        SequenceItem(
            rank=index,
            task_id=task_id,
            readiness=ReadinessState.READY,
            score=SequenceScore(
                task_id=task_id,
                priority_score=100 - index,
                critical_path_score=0,
                deadline_score=0,
                risk_score=0,
                unblock_score=0,
                duration_score=0,
                total_score=100 - index,
            ),
            dependency_depth=0,
            downstream_count=0,
            on_critical_path=False,
        )
        for index, task_id in enumerate(task_ids, 1)
    )
    return ControlSnapshot(
        snapshot_id=control_identifier("CTRL", "director-selection"),
        project_id="PROJECT-PIPELINE",
        sequence=BuildSequence(
            sequence_id=control_identifier("SEQ", "director-selection"),
            project_id="PROJECT-PIPELINE",
            graph_fingerprint="d" * 64,
            task_count=len(items),
            edge_count=0,
            ready_count=len(items),
            active_count=0,
            blocked_count=0,
            critical_path=CriticalPathAnalysis(
                path=(),
                total_duration_minutes=0,
                duration_source="EMPTY",
                earliest_finish_minutes={},
                slack_minutes={},
            ),
            ordered_ready_work=items,
            generated_at_utc=now,
        ),
        scope=ScopeReconciliationReport(
            report_id=control_identifier("SCOPE", "director-selection"),
            project_id="PROJECT-PIPELINE",
            requirement_count=0,
            work_item_count=len(items),
            findings=(),
            fingerprint="e" * 64,
            generated_at_utc=now,
        ),
        completion=CompletionProjection(
            projection_id=control_identifier("COMPLETE", "director-selection"),
            project_id="PROJECT-PIPELINE",
            state=CompletionProjectionState.INCOMPLETE,
            total_work_items=len(items),
            completed_work_items=0,
            active_work_items=0,
            blocked_work_items=0,
            failed_work_items=0,
            accepted_requirements=0,
            implemented_or_external_blocked_requirements=0,
            ready_work_items=len(items),
            verification_eligible=False,
            reasons=("director selection uses Control-ready work only",),
            generated_at_utc=now,
        ),
        eligibility=tuple(
            TaskEligibility(task_id=task_id, state=EligibilityState.ELIGIBLE, eligible=True)
            for task_id in task_ids
        ),
        readiness=tuple(
            TaskReadiness(task_id=task_id, state=ReadinessState.READY, ready=True)
            for task_id in task_ids
        ),
        snapshot_fingerprint="f" * 64,
        generated_at_utc=now,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persistent Autonomy Director process helper")
    parser.add_argument("action", choices=("select", "recover", "project"))
    parser.add_argument("--state", required=True)
    parser.add_argument("--ready", action="append", default=[])
    args = parser.parse_args(argv)
    director = PersistentAutonomyDirector(Path(args.state))
    if args.action == "select":
        decision = director.select_next_work(control_snapshot_for_selection(tuple(args.ready)))
        print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.action == "recover":
        print(json.dumps(director.recover(), sort_keys=True))
        return 0
    print(json.dumps(director.projection(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
