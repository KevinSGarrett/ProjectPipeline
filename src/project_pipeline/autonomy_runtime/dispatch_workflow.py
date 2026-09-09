"""Single production path: place, claim, persist intent, dispatch, accept."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.lifecycle import FleetLifecycleJournal
from project_pipeline.autonomy_runtime.remote_job import RemoteJobController, RemoteJobEnvelope
from project_pipeline.autonomy_runtime.ssh_dispatch import SshDispatchAdapter
from project_pipeline.autonomy_runtime.windows_limits import nested_pool_env
from project_pipeline.scheduler.admission import chosen_host_admitted, load_admission_record
from project_pipeline.scheduler.fleet import (
    MachineProfile,
    physical_claims_for_machine,
    select_target,
)
from project_pipeline.scheduler.persistence import SchedulerStore


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
        chosen, denials = select_target(
            candidates or self.profiles,
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
        try:
            return self._dispatch_with_bundle(
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
        finally:
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
            input_sha256=input_sha256,
            argv=argv,
            workspace=workspace,
            workspace_root=workspace_root,
            deadline_utc=now + timedelta(minutes=15),
            cpu_ceiling=cpu,
            memory_mb_ceiling=memory_mb,
            correlation_id=holder_id,
            output_contract_sha256=output_contract_sha256,
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
        nested_pool_env(cpu)
        worker = adapter or self.adapter_factory(chosen.machine_id)
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
        accepted = controller.accept(
            envelope, executed["result"], expected_host=chosen.machine_id, now=now
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
        }
