"""Declared versus observed three-host fleet profiles.

OpenSSH on WIN-EVSH1DN8H5O is Windows Win32-OpenSSH bound to Tailscale, not
Tailscale SSH-server. Declared records without an observation source stay stale.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from project_pipeline.scheduler.fleet import MachineProfile

UNOBSERVED_AT = datetime(1970, 1, 1, tzinfo=UTC)
XEON_MACHINE_ID = "WIN-EVSH1DN8H5O"
XEON_TTL_SECONDS = 3600
GIB_TO_MIB = 1024

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
        "ttl_seconds": 300,
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
        "ttl_seconds": 300,
        "tailnet_ipv4": "100.77.151.3",
        "bootstrap_precondition": (
            "Do not retry denied kevin@ or kines@ keys on COMFY-V4-CPU-01. "
            "TCP/22 is open; install an authorized OpenSSH principal on-box."
        ),
    },
    {
        "machine_id": XEON_MACHINE_ID,
        "hostname": "WIN-EVSH1DN8H5O",
        "role": "MEMORY_HEAVY_BATCH_WORKER",
        "state": "READY",
        "os_family": "windows",
        "isa_flags": ("avx",),
        "cuda_compute_capability": 2.0,
        "gpu_name": "Quadro 6000",
        "cpu_slots": 16,
        "memory_mb": 65495,
        "disk_mb": 70082,
        "principal": r"win-evsh1dn8h5o\kines",
        "modern_cuda_eligible": False,
        "ttl_seconds": XEON_TTL_SECONDS,
        "tailnet_ipv4": "100.107.207.66",
        "bootstrap_precondition": None,
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


def declared_profiles(
    *, when: datetime | None = None, observation_source: str | None = None
) -> tuple[MachineProfile, ...]:
    observed = (when or datetime.now(UTC)).astimezone(UTC) if observation_source else UNOBSERVED_AT
    return tuple(
        MachineProfile(
            machine_id=str(item["machine_id"]),
            hostname=str(item["hostname"]),
            role=str(item["role"]),
            state=str(item["state"]),
            observed_at_utc=observed,
            ttl_seconds=int(item["ttl_seconds"]),
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
        for item in DECLARED_HOSTS
    )


def _matches_local_hostname(profile: MachineProfile, hostname: str) -> bool:
    names = {profile.hostname.upper(), profile.machine_id.upper()}
    if profile.role == "PRIMARY_CONTROL_CANDIDATE":
        names.add("KEVIN")
    return hostname in names


def apply_local_control_observation(
    profiles: tuple[MachineProfile, ...], *, when: datetime | None = None
) -> tuple[MachineProfile, ...]:
    """Stamp freshness only for the workstation this process is actually running on."""

    hostname = socket.gethostname().upper()
    observed = (when or datetime.now(UTC)).astimezone(UTC)
    return tuple(
        profile.model_copy(update={"observed_at_utc": observed})
        if _matches_local_hostname(profile, hostname)
        else profile
        for profile in profiles
    )


def _isa_flags_from_inventory(inventory: Mapping[str, Any]) -> tuple[str, ...]:
    isa = inventory.get("isa")
    flags: list[str] = []
    if isinstance(isa, Mapping):
        if isa.get("sse42"):
            flags.append("sse42")
        if isa.get("avx"):
            flags.append("avx")
        if isa.get("avx2"):
            flags.append("avx2")
        return tuple(flags)
    return ("avx",)


def profile_from_xeon_inventory(
    inventory: Mapping[str, Any], *, when: datetime | None = None
) -> MachineProfile | None:
    hostname = str(inventory.get("hostname") or "").strip().upper()
    if hostname != XEON_MACHINE_ID:
        return None
    disks = inventory.get("disks")
    disk = disks[0] if isinstance(disks, list) and disks else {}
    free_gb = float(disk.get("FreeGB") or 0) if isinstance(disk, Mapping) else 0.0
    gpu_rows = inventory.get("gpus")
    gpu = gpu_rows[0] if isinstance(gpu_rows, list) and gpu_rows else {}
    gpu_name = str(gpu.get("Name") or "Quadro 6000") if isinstance(gpu, Mapping) else "Quadro 6000"
    classification = classify_gpu(name=gpu_name, compute_capability=2.0)
    observed = (when or datetime.now(UTC)).astimezone(UTC)
    ram_gb = float(inventory.get("totalRAMGB") or 63.96)
    logical = int(inventory.get("cpuLogical") or 16)
    return MachineProfile(
        machine_id=XEON_MACHINE_ID,
        hostname="WIN-EVSH1DN8H5O",
        role="MEMORY_HEAVY_BATCH_WORKER",
        state="READY",
        observed_at_utc=observed,
        ttl_seconds=XEON_TTL_SECONDS,
        os_family="windows",
        isa_flags=_isa_flags_from_inventory(inventory),
        cuda_compute_capability=2.0,
        gpu_name=gpu_name.replace("NVIDIA ", ""),
        cpu_slots=max(1, logical),
        memory_mb=max(1, int(ram_gb * GIB_TO_MIB)),
        disk_mb=max(1, int(free_gb * GIB_TO_MIB)),
        principal=str(inventory.get("whoami") or r"win-evsh1dn8h5o\kines"),
        modern_cuda_eligible=bool(classification["modern_cuda_eligible"]),
    )


def apply_inventory_observation(
    profiles: tuple[MachineProfile, ...],
    inventory: Mapping[str, Any],
    *,
    when: datetime | None = None,
) -> tuple[MachineProfile, ...]:
    observed = profile_from_xeon_inventory(inventory, when=when)
    if observed is None:
        return profiles
    return tuple(observed if item.machine_id == XEON_MACHINE_ID else item for item in profiles)


def enrollment_blockers() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "machine_id": str(item["machine_id"]),
            "bootstrap_precondition": str(item["bootstrap_precondition"]),
        }
        for item in DECLARED_HOSTS
        if item.get("bootstrap_precondition")
    )
