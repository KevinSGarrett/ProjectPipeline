"""Declared versus observed three-host fleet profiles.

OpenSSH on WIN-EVSH1DN8H5O and COMFY-V4-CPU-01 is Windows Win32-OpenSSH bound to
Tailscale, not Tailscale SSH-server. Declared records without an observation
source stay stale.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import socket
import subprocess
from collections.abc import Mapping
from ctypes import wintypes
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
    """Declared records stay unmeasured. An observation_source name cannot renew health."""

    del when, observation_source
    return tuple(
        MachineProfile(
            machine_id=str(item["machine_id"]),
            hostname=str(item["hostname"]),
            role=str(item["role"]),
            state=str(item["state"]),
            observed_at_utc=UNOBSERVED_AT,
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
            observation_kind="DECLARED",
            os_support_status="UNSUPPORTED_21H1" if item["machine_id"] == XEON_MACHINE_ID else None,
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
    """Hostname match alone cannot mint READY capacity."""

    del when
    hostname = socket.gethostname().upper()
    return tuple(
        profile.model_copy(update={"observation_kind": "HOSTNAME_ONLY"})
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


def _inventory_complete(inventory: Mapping[str, Any]) -> bool:
    required = ("hostname", "whoami", "sid", "totalRAMGB", "cpuLogical", "disks", "isa")
    if any(not inventory.get(key) for key in required):
        return False
    measured_at = inventory.get("measured_at_utc")
    return measured_at is not None


def _mark_inventory_complete(payload: dict[str, Any]) -> dict[str, Any]:
    payload["ok"] = True
    payload["observation_kind"] = "MEASURED" if _inventory_complete(payload) else "PARTIAL"
    return payload


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
    complete = _inventory_complete(inventory)
    ram_gb = inventory.get("totalRAMGB")
    logical = inventory.get("cpuLogical")
    whoami = inventory.get("whoami")
    measured_at = inventory.get("measured_at_utc")
    observed_at = UNOBSERVED_AT
    if measured_at:
        try:
            observed_at = datetime.fromisoformat(
                str(measured_at).replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            observed_at = UNOBSERVED_AT
            complete = False
    current = (when or datetime.now(UTC)).astimezone(UTC)
    if observed_at.year <= 1970 or observed_at > current + timedelta(seconds=300):
        complete = False
        kind_override = "PARTIAL"
    else:
        kind_override = None
    if ram_gb is None or logical is None or not whoami:
        kind = "PARTIAL"
        ram_gb = default_ram_gb
        logical = default_logical
        whoami = default_principal
    else:
        kind = "MEASURED" if complete else "PARTIAL"
    if kind_override:
        kind = kind_override
    del when
    available_ram = inventory.get("availableRAMGB")
    physical = inventory.get("cpuPhysical")
    return MachineProfile(
        machine_id=machine_id,
        hostname=str(inventory.get("hostname") or machine_id),
        role=role,
        state="READY" if kind == "MEASURED" else "STALE",
        observed_at_utc=observed_at,
        ttl_seconds=ttl_seconds,
        os_family="windows",
        isa_flags=_isa_flags_from_inventory(inventory),
        cuda_compute_capability=compute_capability,
        gpu_name=gpu_name,
        cpu_slots=max(1, int(logical)),
        memory_mb=max(1, int(float(ram_gb) * GIB_TO_MIB)),
        disk_mb=max(1, int(_inventory_disk_free_gb(inventory) * GIB_TO_MIB)),
        principal=str(whoami),
        modern_cuda_eligible=bool(classification["modern_cuda_eligible"]),
        observation_kind=kind,
        available_memory_mb=(
            max(1, int(float(available_ram) * GIB_TO_MIB)) if available_ram is not None else None
        ),
        sid=str(inventory["sid"]) if inventory.get("sid") else None,
        os_build=str(inventory["osBuild"]) if inventory.get("osBuild") else None,
        os_support_status=(
            str(inventory["osSupportStatus"])
            if inventory.get("osSupportStatus")
            else ("UNSUPPORTED_21H1" if str(inventory.get("osBuild") or "") == "19043" else None)
        ),
        cpu_physical_cores=int(physical) if physical is not None else None,
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


PRIMARY_MACHINE_ID = "PRIMARY-CODEX-WORKSTATION"
PRIMARY_HOSTNAMES = frozenset({"KEVIN", PRIMARY_MACHINE_ID})


def profile_from_primary_inventory(
    inventory: Mapping[str, Any], *, when: datetime | None = None
) -> MachineProfile | None:
    token = _hostname_token(inventory)
    if token not in PRIMARY_HOSTNAMES and not inventory.get("control_host"):
        return None
    gpu = _inventory_first_row(inventory, "gpus")
    gpu_name = str(gpu.get("Name") or "RTX 5060") if isinstance(gpu, Mapping) else "RTX 5060"
    return _observed_worker_profile(
        inventory,
        machine_id=PRIMARY_MACHINE_ID,
        role="PRIMARY_CONTROL_CANDIDATE",
        ttl_seconds=300,
        gpu_name=gpu_name.replace("NVIDIA ", ""),
        compute_capability=12.0,
        default_ram_gb=31.25,
        default_logical=16,
        default_principal="operator:control",
        when=when,
    )


def apply_inventory_observation(
    profiles: tuple[MachineProfile, ...],
    inventory: Mapping[str, Any],
    *,
    when: datetime | None = None,
) -> tuple[MachineProfile, ...]:
    for builder in (
        profile_from_xeon_inventory,
        profile_from_comfy_inventory,
        profile_from_primary_inventory,
    ):
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


def detect_isa_flags() -> dict[str, bool]:
    """Best-effort ISA flags. Missing AVX2 detection stays False rather than guessed True."""

    flags = {"sse42": False, "avx": False, "avx2": False}
    if os.name != "nt":
        return flags
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    present = kernel32.IsProcessorFeaturePresent
    present.argtypes = [wintypes.DWORD]
    present.restype = wintypes.BOOL
    flags["sse42"] = bool(present(10))
    flags["avx"] = bool(present(39))
    return flags


_MEASURE_QUERY = r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$disks = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
    Select-Object DeviceID, FreeSpace, Size)
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$isa = $null
try {
    $isa = [pscustomobject]@{
        sse42 = [System.Runtime.Intrinsics.X86.Sse42]::IsSupported
        avx = [System.Runtime.Intrinsics.X86.Avx]::IsSupported
        avx2 = [System.Runtime.Intrinsics.X86.Avx2]::IsSupported
    }
} catch {
    $isa = $null
}
if ($null -eq $isa) {
    try {
        if (-not ('PpCpuId' -as [type])) {
            Add-Type -TypeDefinition @"
using System.Runtime.InteropServices;
public static class PpCpuId {
    [DllImport("kernel32.dll")]
    public static extern bool IsProcessorFeaturePresent(uint feature);
}
"@
        }
        $isa = [pscustomobject]@{
            sse42 = [PpCpuId]::IsProcessorFeaturePresent(10)
            avx = [PpCpuId]::IsProcessorFeaturePresent(39)
            avx2 = $false
        }
    } catch {
        $isa = $null
    }
}
$cpuPhysical = @($cpu.NumberOfCores)[0]
if (-not $cpuPhysical) { $cpuPhysical = $cs.NumberOfProcessors }
$row = [pscustomobject]@{
    hostname = $env:COMPUTERNAME
    whoami = $identity.Name
    sid = $identity.User.Value
    totalRAMGB = [math]::Round(($os.TotalVisibleMemorySize / 1MB), 2)
    availableRAMGB = [math]::Round(($os.FreePhysicalMemory / 1MB), 2)
    cpuLogical = $cs.NumberOfLogicalProcessors
    cpuPhysical = $cpuPhysical
    osBuild = $os.BuildNumber
    osSupportStatus = if ($os.BuildNumber -eq '19043') { 'UNSUPPORTED_21H1' } else { $null }
    disks = @($disks | ForEach-Object {
        [pscustomobject]@{ DeviceID = $_.DeviceID; FreeGB = [math]::Round(($_.FreeSpace / 1GB), 2) }
    })
    isa = $isa
    measured_at_utc = [DateTime]::UtcNow.ToString('o')
}
$row | ConvertTo-Json -Compress -Depth 5
"""


def measure_local_inventory(*, query: Any = None) -> dict[str, Any]:
    """Measure this host. Observation time is the CIM measurement time, not ingest time."""

    if query is None:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _MEASURE_QUERY],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            return {"ok": False, "reason": "measurement_unavailable", "observation_kind": "PARTIAL"}
        raw = completed.stdout or "{}"
    else:
        raw = query(_MEASURE_QUERY)
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not payload.get("measured_at_utc"):
        return {"ok": False, "reason": "measurement_incomplete", "observation_kind": "PARTIAL"}
    if not payload.get("isa") and query is None:
        payload["isa"] = detect_isa_flags()
    return _mark_inventory_complete(payload)


def measure_remote_inventory(
    *, host: str, user: str, identity: Path | None = None
) -> dict[str, Any]:
    """Measure an enrolled worker through OpenSSH. Observation time is the remote CIM time."""

    allowed = {
        item["host"]: item["user"]
        for item in (
            {"host": "100.107.207.66", "user": "kines"},
            {"host": "100.77.151.3", "user": "Windows 11"},
        )
    }
    if allowed.get(host) != user:
        return {"ok": False, "reason": "unknown_ssh_target", "observation_kind": "PARTIAL"}
    key = identity or (Path.home() / ".ssh" / "id_ed25519")
    if not key.is_file():
        return {"ok": False, "reason": "ssh_identity_missing", "observation_kind": "PARTIAL"}
    encoded = base64.b64encode(_MEASURE_QUERY.encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        [
            "ssh",
            "-i",
            str(key),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-l",
            user,
            host,
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "reason": "remote_measurement_unavailable",
            "observation_kind": "PARTIAL",
            "exit_code": completed.returncode,
        }
    try:
        payload = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {
            "ok": False,
            "reason": "remote_measurement_unparseable",
            "observation_kind": "PARTIAL",
        }
    if not isinstance(payload, dict) or not payload.get("measured_at_utc"):
        return {"ok": False, "reason": "measurement_incomplete", "observation_kind": "PARTIAL"}
    payload["tailnet_host"] = host
    return _mark_inventory_complete(payload)
