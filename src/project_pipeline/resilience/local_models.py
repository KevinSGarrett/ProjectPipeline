from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from urllib.parse import urlparse

from project_pipeline.domain.resilience import LocalRuntimeSpec, RuntimeKind, resilience_identifier


def _local_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.hostname in {"localhost", "host.docker.internal"}:
        return True
    try:
        return (
            ipaddress.ip_address(parsed.hostname).is_private
            or ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        return False


def load_local_runtimes(root: Path) -> tuple[LocalRuntimeSpec, ...]:
    data = json.loads((root / "config/resilience_policy.json").read_text(encoding="utf-8"))
    rows = []
    for item in data["local_model_runtimes"]:
        rows.append(
            LocalRuntimeSpec(
                runtime_id=resilience_identifier("RUNTIME", item["kind"], item["endpoint"]),
                kind=RuntimeKind(item["kind"]),
                endpoint=item["endpoint"],
                capabilities=tuple(item["capabilities"]),
                qualified=bool(item.get("qualified", False)),
                remote_network_allowed=bool(item.get("remote_network_allowed", False)),
                metadata={str(k): str(v) for k, v in item.get("metadata", {}).items()},
            )
        )
    return tuple(rows)


class LocalModelGateway:
    """Provider-neutral local inference selection. Deterministic authority remains outside the model runtime."""

    def __init__(self, runtimes: tuple[LocalRuntimeSpec, ...]) -> None:
        self.runtimes = runtimes

    def validate(self) -> list[str]:
        errors = []
        for runtime in self.runtimes:
            if not runtime.remote_network_allowed and not _local_endpoint(runtime.endpoint):
                errors.append(f"runtime {runtime.runtime_id} endpoint is not local/private")
            if not runtime.advisory_only:
                errors.append(f"runtime {runtime.runtime_id} attempted deterministic authority")
        return errors

    def select(
        self,
        required_capabilities: tuple[str, ...],
        *,
        available_kinds: tuple[RuntimeKind, ...] | None = None,
    ) -> LocalRuntimeSpec | None:
        required = set(required_capabilities)
        allowed = set(available_kinds or tuple(RuntimeKind))
        # Prefer explicitly qualified runtime, then stable config order. A non-qualified selection is a plan, not a live-qualification claim.
        eligible = [
            r for r in self.runtimes if r.kind in allowed and required.issubset(set(r.capabilities))
        ]
        eligible.sort(key=lambda r: (not r.qualified, self.runtimes.index(r)))
        return eligible[0] if eligible else None

    def plan_request(
        self, runtime: LocalRuntimeSpec, *, model: str, task_kind: str
    ) -> dict[str, object]:
        if runtime not in self.runtimes:
            raise ValueError("runtime is not registered")
        if not runtime.remote_network_allowed and not _local_endpoint(runtime.endpoint):
            raise ValueError("runtime endpoint violates local/private policy")
        return {
            "runtime_id": runtime.runtime_id,
            "runtime_kind": runtime.kind.value,
            "endpoint": runtime.endpoint,
            "model": model,
            "task_kind": task_kind,
            "advisory_only": True,
            "deterministic_control_authority": False,
            "live_invocation_performed": False,
        }
