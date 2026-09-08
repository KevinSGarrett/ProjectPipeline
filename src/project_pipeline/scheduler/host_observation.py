"""Declared versus observed three-host fleet profiles.

Live SSH enrollment of WIN-EVSH1DN8H5O is a separate operator action. This module
never treats an unauthenticated Tailscale host as an admitted worker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from project_pipeline.scheduler.fleet import MachineProfile

DECLARED_HOSTS: tuple[dict[str, Any], ...] = (
    {
        "machine_id": "PRIMARY-CODEX-WORKSTATION",
        "hostname": "KEVIN",
        "role": "PRIMARY_CONTROL_CANDIDATE",
        "state": "READY",
        "os_family": "windows",
        "isa_flags": ("avx", "avx2"),
        "cuda_compute_capability": 12.0,
        "gpu_name": "RTX 5060",
        "cpu_slots": 16,
        "memory_mb": 32000,
        "disk_mb": 200000,
        "principal": "operator:control",
        "modern_cuda_eligible": True,
        "tailnet_ipv4": None,
        "bootstrap_precondition": None,
    },
    {
        "machine_id": "COMFY-V4-CPU-01",
        "hostname": "COMFY-V4-CPU-01",
        "role": "CPU_WORKER",
        "state": "READY",
        "os_family": "windows",
        "isa_flags": ("avx", "avx2"),
        "cuda_compute_capability": None,
        "gpu_name": None,
        "cpu_slots": 8,
        "memory_mb": 32000,
        "disk_mb": 24780,
        "principal": "worker:comfy",
        "modern_cuda_eligible": False,
        "tailnet_ipv4": "100.77.151.3",
        "bootstrap_precondition": None,
    },
    {
        "machine_id": "WIN-EVSH1DN8H5O",
        "hostname": "WIN-EVSH1DN8H5O",
        "role": "MEMORY_HEAVY_BATCH_WORKER",
        "state": "ENROLLMENT_PENDING",
        "os_family": "windows",
        "isa_flags": ("avx",),
        "cuda_compute_capability": 2.0,
        "gpu_name": "Quadro 6000",
        "cpu_slots": 16,
        "memory_mb": 64000,
        "disk_mb": 100000,
        "principal": "worker:unenrolled",
        "modern_cuda_eligible": False,
        "tailnet_ipv4": "100.107.207.66",
        "bootstrap_precondition": (
            "Enable Windows OpenSSH Server on WIN-EVSH1DN8H5O, bind it to the "
            "Tailscale interface 100.107.207.66, and authorize the existing "
            "operator principal. Do not use Tailscale SSH-server as the Windows "
            "transport, and do not copy .env files."
        ),
    },
)


def classify_gpu(*, name: str | None, compute_capability: float | None) -> dict[str, Any]:
    if name and "quadro 6000" in name.lower():
        return {
            "modern_cuda_eligible": False,
            "reason": "Fermi CC2.0 last supported by CUDA 8 / R390; modern ML dispatch must reject it",
        }
    if compute_capability is not None and compute_capability < 5.0:
        return {
            "modern_cuda_eligible": False,
            "reason": f"compute capability {compute_capability} is below modern CUDA minimum 5.0",
        }
    if compute_capability is None:
        return {"modern_cuda_eligible": False, "reason": "no discrete CUDA GPU observed"}
    return {"modern_cuda_eligible": True, "reason": "modern CUDA eligible"}


def declared_profiles(*, when: datetime | None = None) -> tuple[MachineProfile, ...]:
    observed = (when or datetime.now(UTC)).astimezone(UTC)
    profiles: list[MachineProfile] = []
    for item in DECLARED_HOSTS:
        profiles.append(
            MachineProfile(
                machine_id=str(item["machine_id"]),
                hostname=str(item["hostname"]),
                role=str(item["role"]),
                state=str(item["state"]),
                observed_at_utc=observed,
                os_family=str(item["os_family"]),
                isa_flags=tuple(item["isa_flags"]),
                cuda_compute_capability=item["cuda_compute_capability"],
                gpu_name=item["gpu_name"],
                cpu_slots=int(item["cpu_slots"]),
                memory_mb=int(item["memory_mb"]),
                disk_mb=int(item["disk_mb"]),
                principal=str(item["principal"]),
                modern_cuda_eligible=bool(item["modern_cuda_eligible"]),
            )
        )
    return tuple(profiles)


def enrollment_blockers() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "machine_id": str(item["machine_id"]),
            "bootstrap_precondition": str(item["bootstrap_precondition"]),
        }
        for item in DECLARED_HOSTS
        if item.get("bootstrap_precondition")
    )
