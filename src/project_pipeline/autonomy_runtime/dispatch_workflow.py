"""Single production path: place, claim, persist intent, dispatch, accept."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.context_validation import (
    compile_validation_pack,
    consume_pack_on_worker,
    job_input_digest,
    junit_case_counts_from_bytes,
    write_pack,
)
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore, digest_bytes
from project_pipeline.autonomy_runtime.lifecycle import FleetLifecycleJournal
from project_pipeline.autonomy_runtime.remote_job import RemoteJobController, RemoteJobEnvelope
from project_pipeline.autonomy_runtime.remote_worker_protocol import write_lease_grant
from project_pipeline.autonomy_runtime.ssh_dispatch import SshDispatchAdapter, job_stdout_metrics
from project_pipeline.autonomy_runtime.task_execution_specs import required_tests
from project_pipeline.autonomy_runtime.windows_limits import nested_pool_env
from project_pipeline.autonomy_runtime.worker_allowlist import CYCLE_OWNED_VALIDATION_JOBS
from project_pipeline.scheduler.admission import chosen_host_admitted, load_admission_record
from project_pipeline.scheduler.fleet import (
    MachineProfile,
    physical_claims_for_machine,
    select_target,
)
from project_pipeline.scheduler.persistence import SchedulerStore


def _acquire_job_artifact(adapter: Any, workspace: str, dest: Path) -> bytes | None:
    acquire = getattr(adapter, "acquire_workspace_file", None)
    if callable(acquire):
        return acquire(Path(workspace), "junit.xml", dest)
    local = Path(workspace) / "junit.xml"
    if local.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = local.read_bytes()
        dest.write_bytes(payload)
        return payload
    return None


class DispatchWorkflow:
    def __init__(
        self,
        *,
        store: SchedulerStore,
        jobs: FleetJobStore,
        profiles: tuple[MachineProfile, ...],
        admission_path: Path,
        source_sha: str,
        source_tree: str,
        overlay_sha256: str,
        adapter_factory: Any = SshDispatchAdapter.for_machine,
        journal: FleetLifecycleJournal | None = None,
    ) -> None:
        self.store = store
        self.jobs = jobs
        self.profiles = profiles
        self.admission_path = admission_path
        self.source_sha = source_sha
        self.source_tree = source_tree
        self.overlay_sha256 = overlay_sha256
        self.adapter_factory = adapter_factory
        self.journal = journal

    def dispatch(
        self,
        *,
        task_id: str,
        holder_id: str,
        argv: tuple[str, ...],
        workspace: str,
        workspace_root: str,
        principal: str,
        input_sha256: str,
        now: datetime | None = None,
        require_avx2: bool = False,
        require_modern_cuda: bool = False,
        cpu: int = 1,
        memory_mb: int = 256,
        adapter: Any = None,
        output_contract_sha256: str | None = None,
        machine_id: str | None = None,
    ) -> dict[str, Any]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        record = load_admission_record(self.admission_path)
        candidates = self.profiles
        if machine_id:
            candidates = tuple(item for item in self.profiles if item.machine_id == machine_id)
            if not candidates:
                return {
                    "outcome": "REJECTED",
                    "reason": "unknown_machine",
                    "denials": (f"unknown_machine:{machine_id}",),
                }
        chosen, denials = select_target(
            candidates,
            when=now,
            require_avx2=require_avx2,
            require_modern_cuda=require_modern_cuda,
        )
        if chosen is None:
            return {"outcome": "REJECTED", "reason": "no_eligible_host", "denials": denials}
        gate = chosen_host_admitted(
            record,
            chosen.machine_id,
            expected_sha=self.source_sha,
            expected_tree=self.source_tree,
            now=now,
            cycle_owned=task_id in CYCLE_OWNED_VALIDATION_JOBS,
        )
        if not gate["ok"]:
            return {
                "outcome": "REJECTED",
                "reason": "admission_denied",
                "failures": list(gate["failures"]),
                "denials": denials,
            }
        self.store.ensure_machine_pools(chosen.physical_pools())
        bundle = self.store.acquire_bundle(
            task_id=task_id,
            holder_id=holder_id,
            claims=physical_claims_for_machine(chosen.machine_id, cpu=cpu, memory_mb=memory_mb),
            now=now,
        )
        if not bundle.acquired:
            return {
                "outcome": "REJECTED",
                "reason": "lease_denied",
                "failures": list(bundle.reasons),
            }
        fence = str(bundle.leases[0].fencing_token)
        lease_id = bundle.leases[0].lease_id
        outcome: dict[str, Any] | None = None
        try:
            outcome = self._dispatch_with_bundle(
                task_id=task_id,
                holder_id=holder_id,
                argv=argv,
                workspace=workspace,
                workspace_root=workspace_root,
                principal=principal,
                input_sha256=input_sha256,
                now=now,
                cpu=cpu,
                memory_mb=memory_mb,
                adapter=adapter,
                output_contract_sha256=output_contract_sha256,
                chosen=chosen,
                denials=denials,
                fence=fence,
                lease_id=lease_id,
            )
            return outcome
        finally:
            if outcome is not None and outcome.get("outcome") in {"ACCEPTED", "REJECTED"}:
                for lease in bundle.leases:
                    self.store.release_lease(
                        lease.lease_id,
                        holder_id=holder_id,
                        fencing_token=lease.fencing_token,
                        now=now,
                    )

    def _dispatch_with_bundle(
        self,
        *,
        task_id: str,
        holder_id: str,
        argv: tuple[str, ...],
        workspace: str,
        workspace_root: str,
        principal: str,
        input_sha256: str,
        now: datetime,
        cpu: int,
        memory_mb: int,
        adapter: Any,
        output_contract_sha256: str | None,
        chosen: MachineProfile,
        denials: tuple[str, ...],
        fence: str,
        lease_id: str,
    ) -> dict[str, Any]:
        del denials
        pack_payload: dict[str, Any] | None = None
        pack_digest = ""
        try:
            selection = required_tests(task_id)
        except ValueError as error:
            return {
                "outcome": "REJECTED",
                "reason": str(error),
                "lifecycle": "REJECTED",
                "host_id": chosen.machine_id,
                "lease_id": lease_id,
                "fence": fence,
            }
        try:
            compiled = compile_validation_pack(
                root=self.store.root,
                database=Path(self.store.database),
                task_id=task_id,
                source_sha=self.source_sha,
                source_tree=self.source_tree,
                overlay_sha256=self.overlay_sha256,
                selection=selection,
                host_id=chosen.machine_id,
                principal=principal or chosen.principal,
            )
        except (OSError, ValueError, RuntimeError, TypeError):
            compiled = {"ok": False}
        if compiled.get("ok") and isinstance(compiled.get("pack"), dict):
            pack_payload = compiled["pack"]
            pack_digest = str(compiled.get("pack_sha256") or "")
        if not pack_payload or len(pack_digest) != 64:
            return {
                "outcome": "REJECTED",
                "reason": "context_pack_compile_failed",
                "lifecycle": "REJECTED",
                "host_id": chosen.machine_id,
                "lease_id": lease_id,
                "fence": fence,
            }
        nested_pool_env(cpu)
        worker = adapter or self.adapter_factory(chosen.machine_id)
        remote_worker = isinstance(worker, SshDispatchAdapter) or bool(
            getattr(worker, "remote_host", False)
        )
        local_workspace = Path(workspace).is_dir() and not remote_worker
        require_pack = True
        canonical_input = job_input_digest(
            task_id=task_id,
            source_sha=self.source_sha,
            source_tree=self.source_tree,
            overlay_sha256=self.overlay_sha256,
            pack_sha256=pack_digest,
            selection=selection,
        )
        del input_sha256
        grant = {
            "lease_id": lease_id,
            "fence": fence,
            "job_id": task_id,
            "host_id": chosen.machine_id,
            "status": "ACTIVE",
            "source_sha": self.source_sha,
            "source_tree": self.source_tree,
            "overlay_sha256": self.overlay_sha256,
        }
        envelope = RemoteJobEnvelope(
            job_id=task_id,
            host_id=chosen.machine_id,
            profile_id=chosen.role,
            principal=principal or chosen.principal,
            lease_id=lease_id,
            fence=fence,
            source_sha=self.source_sha,
            source_tree=self.source_tree,
            overlay_sha256=self.overlay_sha256,
            input_sha256=canonical_input,
            argv=argv,
            workspace=workspace,
            workspace_root=workspace_root,
            deadline_utc=now + timedelta(minutes=15),
            cpu_ceiling=cpu,
            memory_mb_ceiling=memory_mb,
            correlation_id=holder_id,
            output_contract_sha256=output_contract_sha256,
            context_pack=pack_payload if require_pack else None,
            pack_sha256=pack_digest or None if require_pack else None,
            require_context_consumption=require_pack,
            test_selection=selection,
            lease_grant=grant,
        )
        if Path(workspace).is_dir():
            write_lease_grant(Path(workspace), grant)
        placer = getattr(worker, "place_workspace_file", None)
        if callable(placer):
            placer(
                Path(workspace),
                "lease_grant.json",
                (json.dumps(grant, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
        intent = self.jobs.persist_intent(envelope.model_dump(mode="json"), now=now)
        if not intent.get("ok"):
            return {"outcome": "REJECTED", "reason": intent.get("reason"), "lifecycle": "REJECTED"}
        if self.journal is not None:
            self.journal.publish(
                {
                    "job_id": task_id,
                    "host_id": chosen.machine_id,
                    "lease_id": lease_id,
                    "fence": fence,
                    "status": "DISPATCHED",
                    "authority": holder_id,
                }
            )
        consumed: dict[str, Any] | None = None
        if require_pack and local_workspace and pack_payload is not None:
            write_pack(Path(workspace), pack_payload)
            consumed = consume_pack_on_worker(
                {
                    "pack_path": str(Path(workspace) / "context_pack.json"),
                    "workspace": str(workspace),
                    "pack_sha256": pack_digest,
                    "source_sha": self.source_sha,
                    "source_tree": self.source_tree,
                    "overlay_sha256": self.overlay_sha256,
                    "host_id": chosen.machine_id,
                    "principal": envelope.principal,
                    "job_id": task_id,
                    "project_id": "PROJECT-PIPELINE",
                }
            )
            if not consumed.get("ok"):
                return {
                    "outcome": "REJECTED",
                    "reason": consumed.get("reason") or "pack_unconsumed",
                    "lifecycle": "REJECTED",
                    "host_id": chosen.machine_id,
                    "lease_id": lease_id,
                    "fence": fence,
                }
        controller = RemoteJobController(
            worker,
            store=self.jobs,
            require_intent=True,
            expected_source_sha=self.source_sha,
            expected_source_tree=self.source_tree,
            expected_overlay_sha256=self.overlay_sha256,
            expected_principal=envelope.principal,
            workspace_root=workspace_root,
        )
        executed = controller.execute(envelope, now=now)
        if executed.get("context_consumption") is None and executed.get("stdout"):
            executed.update(job_stdout_metrics(str(executed.get("stdout") or "")))
        if executed.get("outcome") != "EXECUTED":
            if self.journal is not None:
                self.journal.publish(
                    {
                        "job_id": task_id,
                        "host_id": chosen.machine_id,
                        "lease_id": lease_id,
                        "fence": fence,
                        "status": "UNKNOWN_OUTCOME"
                        if executed.get("outcome") == "UNKNOWN_OUTCOME"
                        else "REJECTED",
                        "authority": holder_id,
                    }
                )
            return {
                "outcome": executed.get("outcome"),
                "reason": executed.get("reason"),
                "lifecycle": "UNKNOWN_OUTCOME"
                if executed.get("outcome") == "UNKNOWN_OUTCOME"
                else "REJECTED",
                "host_id": chosen.machine_id,
                "lease_id": lease_id,
                "fence": fence,
            }
        if self.journal is not None:
            self.journal.publish(
                {
                    "job_id": task_id,
                    "host_id": chosen.machine_id,
                    "lease_id": lease_id,
                    "fence": fence,
                    "status": "RUNNING",
                    "authority": holder_id,
                    "remote_pid": str(executed.get("remote_pid") or ""),
                }
            )
        acquired_dest = Path(self.jobs.database).parent / "acquired" / task_id / "junit.xml"
        artifact_bytes = _acquire_job_artifact(worker, workspace, acquired_dest)
        collected, failed, skipped = (
            junit_case_counts_from_bytes(artifact_bytes) if artifact_bytes else (0, 0, 0)
        )
        if artifact_bytes is None or collected < 1 or failed or skipped:
            reason = (
                "artifact_bytes_required" if artifact_bytes is None else "native_tests_unproven"
            )
            return {
                "outcome": "REJECTED",
                "reason": reason,
                "lifecycle": "REJECTED",
                "host_id": chosen.machine_id,
                "lease_id": lease_id,
                "fence": fence,
            }
        accepted = controller.accept(
            envelope,
            executed["result"],
            expected_host=chosen.machine_id,
            artifact_bytes=artifact_bytes,
            context_consumption=consumed
            if consumed is not None
            else executed.get("context_consumption"),
        )
        lifecycle = (
            "ACCEPTED" if accepted.get("outcome") == "ACCEPTED" else str(accepted.get("reason"))
        )
        if self.journal is not None:
            self.journal.publish(
                {
                    "job_id": task_id,
                    "host_id": chosen.machine_id,
                    "lease_id": lease_id,
                    "fence": fence,
                    "status": lifecycle if lifecycle in {"ACCEPTED", "REJECTED"} else "RECONCILING",
                    "authority": holder_id,
                }
            )
        return {
            "outcome": accepted.get("outcome"),
            "reason": accepted.get("reason"),
            "duplicate": accepted.get("duplicate"),
            "lifecycle": lifecycle,
            "host_id": chosen.machine_id,
            "lease_id": lease_id,
            "fence": fence,
            "executed": executed,
            "tests_run": collected,
            "collected": collected,
            "skipped": skipped,
            "acquired_junit_path": str(acquired_dest),
            "artifact_sha256": digest_bytes(artifact_bytes),
            "junit_sha256": digest_bytes(artifact_bytes),
            "context_consumption": consumed
            if consumed is not None
            else executed.get("context_consumption"),
            "rss_samples_mb": executed.get("rss_samples_mb"),
            "scratch_bytes": executed.get("scratch_bytes"),
            "output_bytes": executed.get("output_bytes"),
            "started_at_utc": executed.get("started_at_utc"),
            "ended_at_utc": executed.get("ended_at_utc"),
        }
