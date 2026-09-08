"""Declared versus observed three-host fleet profiles.

OpenSSH on WIN-EVSH1DN8H5O and COMFY-V4-CPU-01 is Windows Win32-OpenSSH bound to
Tailscale, not Tailscale SSH-server. Declared records without an observation
source stay stale.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from project_pipeline.scheduler.fleet import MachineProfile

UNOBSERVED_AT = datetime(1970, 1, 1, tzinfo=UTC)
XEON_MACHINE_ID = "WIN-EVSH1DN8H5O"
COMFY_MACHINE_ID = "COMFY-V4-CPU-01"
XEON_TTL_SECONDS = 3600
COMFY_TTL_SECONDS = 3600
GIB_TO_MIB = 1024
OPERATIONAL_HOLD_STATES = frozenset({"DRAINED", "QUARANTINED", "OFFLINE"})

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
        "machine_id": COMFY_MACHINE_ID,
        "hostname": "COMFY-V4-CPU-01",
        "role": "CPU_WORKER",
        "state": "READY",
        "os_family": "windows",
        "isa_flags": ("avx", "avx2"),
        "cuda_compute_capability": None,
        "gpu_name": "Intel UHD Graphics 630",
        "cpu_slots": 8,
        "memory_mb": 32552,
        "disk_mb": 29184,
        "principal": r"comfy-v4-cpu-01\windows 11",
        "modern_cuda_eligible": False,
        "ttl_seconds": COMFY_TTL_SECONDS,
        "tailnet_ipv4": "100.77.151.3",
        "bootstrap_precondition": None,
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


def _hostname_token(inventory: Mapping[str, Any]) -> str:
    return str(inventory.get("hostname") or "").strip().upper()


def _inventory_first_row(inventory: Mapping[str, Any], key: str) -> object:
    rows = inventory.get(key)
    return rows[0] if isinstance(rows, list) and rows else {}


def _inventory_disk_free_gb(inventory: Mapping[str, Any]) -> float:
    disk = _inventory_first_row(inventory, "disks")
    return float(disk.get("FreeGB") or 0) if isinstance(disk, Mapping) else 0.0


def _observed_worker_profile(
    inventory: Mapping[str, Any],
    *,
    machine_id: str,
    role: str,
    ttl_seconds: int,
    gpu_name: str | None,
    compute_capability: float | None,
    default_ram_gb: float,
    default_logical: int,
    default_principal: str,
    when: datetime | None,
) -> MachineProfile:
    classification = classify_gpu(name=gpu_name, compute_capability=compute_capability)
    ram_gb = float(inventory.get("totalRAMGB") or default_ram_gb)
    logical = int(inventory.get("cpuLogical") or default_logical)
    return MachineProfile(
        machine_id=machine_id,
        hostname=machine_id,
        role=role,
        state="READY",
        observed_at_utc=(when or datetime.now(UTC)).astimezone(UTC),
        ttl_seconds=ttl_seconds,
        os_family="windows",
        isa_flags=_isa_flags_from_inventory(inventory),
        cuda_compute_capability=compute_capability,
        gpu_name=gpu_name,
        cpu_slots=max(1, logical),
        memory_mb=max(1, int(ram_gb * GIB_TO_MIB)),
        disk_mb=max(1, int(_inventory_disk_free_gb(inventory) * GIB_TO_MIB)),
        principal=str(inventory.get("whoami") or default_principal),
        modern_cuda_eligible=bool(classification["modern_cuda_eligible"]),
    )


def profile_from_xeon_inventory(
    inventory: Mapping[str, Any], *, when: datetime | None = None
) -> MachineProfile | None:
    if _hostname_token(inventory) != XEON_MACHINE_ID:
        return None
    gpu = _inventory_first_row(inventory, "gpus")
    gpu_name = str(gpu.get("Name") or "Quadro 6000") if isinstance(gpu, Mapping) else "Quadro 6000"
    return _observed_worker_profile(
        inventory,
        machine_id=XEON_MACHINE_ID,
        role="MEMORY_HEAVY_BATCH_WORKER",
        ttl_seconds=XEON_TTL_SECONDS,
        gpu_name=gpu_name.replace("NVIDIA ", ""),
        compute_capability=2.0,
        default_ram_gb=63.96,
        default_logical=16,
        default_principal=r"win-evsh1dn8h5o\kines",
        when=when,
    )


def profile_from_comfy_inventory(
    inventory: Mapping[str, Any], *, when: datetime | None = None
) -> MachineProfile | None:
    if _hostname_token(inventory) != COMFY_MACHINE_ID:
        return None
    gpu = _inventory_first_row(inventory, "gpus")
    gpu_name = (
        str(gpu.get("Name") or "Intel UHD Graphics 630") if isinstance(gpu, Mapping) else None
    )
    return _observed_worker_profile(
        inventory,
        machine_id=COMFY_MACHINE_ID,
        role="CPU_WORKER",
        ttl_seconds=COMFY_TTL_SECONDS,
        gpu_name=gpu_name,
        compute_capability=None,
        default_ram_gb=31.79,
        default_logical=8,
        default_principal=r"comfy-v4-cpu-01\windows 11",
        when=when,
    )


def apply_inventory_observation(
    profiles: tuple[MachineProfile, ...],
    inventory: Mapping[str, Any],
    *,
    when: datetime | None = None,
) -> tuple[MachineProfile, ...]:
    for builder in (profile_from_xeon_inventory, profile_from_comfy_inventory):
        observed = builder(inventory, when=when)
        if observed is None:
            continue
        existing = next((item for item in profiles if item.machine_id == observed.machine_id), None)
        if existing is not None and existing.state in OPERATIONAL_HOLD_STATES:
            observed = observed.model_copy(update={"state": existing.state})
        return tuple(
            observed if item.machine_id == observed.machine_id else item for item in profiles
        )
    return profiles


def enrollment_blockers() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "machine_id": str(item["machine_id"]),
            "bootstrap_precondition": str(item["bootstrap_precondition"]),
        }
        for item in DECLARED_HOSTS
        if item.get("bootstrap_precondition")
    )
