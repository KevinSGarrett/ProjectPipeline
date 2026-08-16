from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any


@dataclass(frozen=True, slots=True)
class OpenLITStatus:
    installed: bool
    enabled: bool
    state: str
    upstream_id: str = "UPSTREAM-077"
    version_floor: str = "1.45.0"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def openlit_status(*, enabled: bool, module: Any | None = None) -> OpenLITStatus:
    if not enabled:
        return OpenLITStatus(module is not None, False, "DISABLED")
    try:
        module = module or import_module("openlit")
    except ImportError:
        return OpenLITStatus(False, True, "DEPENDENCY_UNAVAILABLE")
    return OpenLITStatus(True, True, "READY")


def initialize_openlit(
    *,
    enabled: bool,
    otlp_endpoint: str | None = None,
    otlp_headers: str | None = None,
    module: Any | None = None,
) -> Mapping[str, object]:
    status = openlit_status(enabled=enabled, module=module)
    if status.state != "READY":
        return status.as_dict()
    module = module or import_module("openlit")
    kwargs: dict[str, object] = {}
    if otlp_endpoint:
        kwargs["otlp_endpoint"] = otlp_endpoint
    if otlp_headers:
        kwargs["otlp_headers"] = otlp_headers
    module.init(**kwargs)
    return {**status.as_dict(), "state": "INITIALIZED", "endpoint_configured": bool(otlp_endpoint)}
