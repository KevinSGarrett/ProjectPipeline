from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

from project_pipeline.configuration import SecretReference as ConfigSecretReference
from project_pipeline.configuration import SecretResolver
from project_pipeline.domain.security import SecretBackendKind, SecretCapabilityReference
from project_pipeline.upstream_integrations.common import UpstreamIntegrationError
from project_pipeline.upstream_integrations.security import AgeAdapter, SopsAdapter


@dataclass(slots=True)
class EnvFileSecretBackend:
    root: Path
    environment: Mapping[str, str] | None = None
    backend_name: str = "env-file"

    def resolve(self, reference: SecretCapabilityReference) -> str:
        if reference.backend not in {SecretBackendKind.ENVIRONMENT, SecretBackendKind.FILE}:
            raise ValueError("env/file backend received incompatible reference")
        resolver = SecretResolver(self.root, self.environment)
        return resolver.resolve(ConfigSecretReference(reference=reference.reference))


@dataclass(slots=True)
class SopsSecretBackend:
    root: Path
    adapter: SopsAdapter
    backend_name: str = "sops"

    def resolve(self, reference: SecretCapabilityReference) -> str:
        if reference.backend is not SecretBackendKind.SOPS:
            raise ValueError("SOPS backend received incompatible reference")
        target = reference.reference
        if not target.startswith("sops://"):
            raise ValueError("SOPS reference must use sops://")
        spec = target[len("sops://") :]
        path_text, separator, extract = spec.partition("#")
        plan = self.adapter.plan_decrypt(
            self.root, Path(path_text), extract_expression=extract if separator else None
        )
        result = self.adapter.runner(
            plan.argv, Path(plan.cwd), None, self.adapter.timeout_seconds, None
        )
        if result.returncode != 0:
            raise UpstreamIntegrationError("SOPS secret materialization failed")
        value = result.stdout.rstrip("\r\n")
        if not value:
            raise UpstreamIntegrationError("SOPS returned empty secret material")
        return value


@dataclass(slots=True)
class AgeSecretBackend:
    root: Path
    identity_file: Path
    adapter: AgeAdapter
    backend_name: str = "age"

    def resolve(self, reference: SecretCapabilityReference) -> str:
        if reference.backend is not SecretBackendKind.AGE:
            raise ValueError("age backend received incompatible reference")
        target = reference.reference
        if not target.startswith("age-file://"):
            raise ValueError("direct age materialization requires age-file:// reference")
        path = Path(target[len("age-file://") :])
        plan = self.adapter.plan_decrypt(self.root, path, identity_file=self.identity_file)
        result = self.adapter.runner(
            plan.argv, Path(plan.cwd), None, self.adapter.timeout_seconds, None
        )
        if result.returncode != 0:
            raise UpstreamIntegrationError("age secret materialization failed")
        value = result.stdout.rstrip("\r\n")
        if not value:
            raise UpstreamIntegrationError("age returned empty secret material")
        return value


OpenBaoTransport = Callable[[str, str, Mapping[str, str]], tuple[int, str]]
TokenProvider = Callable[[], str]


def _default_openbao_transport(
    method: str, url: str, headers: Mapping[str, str]
) -> tuple[int, str]:
    request = urllib.request.Request(url, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return int(response.status), response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return int(error.code), error.read().decode("utf-8", errors="replace")


@dataclass(slots=True)
class OpenBaoSecretBackend:
    address: str
    token_provider: TokenProvider
    allow_network: bool = False
    transport: OpenBaoTransport = _default_openbao_transport
    backend_name: str = "openbao"

    def __post_init__(self) -> None:
        parsed = urlparse(self.address)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("OpenBao address must be an absolute HTTP(S) URL")
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("non-local OpenBao address must use HTTPS")

    def resolve(self, reference: SecretCapabilityReference) -> str:
        if reference.backend is not SecretBackendKind.OPENBAO:
            raise ValueError("OpenBao backend received incompatible reference")
        if not self.allow_network:
            raise UpstreamIntegrationError("OpenBao network access requires explicit allowance")
        if not reference.reference.startswith("openbao://"):
            raise ValueError("OpenBao reference must use openbao://")
        spec = reference.reference[len("openbao://") :]
        path_text, separator, field = spec.partition("#")
        if not separator or not field or path_text.startswith("/") or ".." in path_text.split("/"):
            raise ValueError("OpenBao reference requires confined path#field")
        token = self.token_provider()
        if not token:
            raise UpstreamIntegrationError("OpenBao token is unavailable")
        url = (
            self.address.rstrip("/")
            + "/v1/"
            + "/".join(quote(part, safe="") for part in path_text.split("/"))
        )
        status, body = self.transport(
            "GET", url, {"X-Vault-Token": token, "Accept": "application/json"}
        )
        if status != 200:
            raise UpstreamIntegrationError(f"OpenBao secret read failed with HTTP {status}")
        try:
            document = json.loads(body)
        except json.JSONDecodeError as error:
            raise UpstreamIntegrationError("OpenBao returned malformed JSON") from error
        data = document.get("data", {})
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        if not isinstance(data, dict) or field not in data:
            raise UpstreamIntegrationError("OpenBao response does not contain requested field")
        value = data[field]
        if not isinstance(value, str) or not value:
            raise UpstreamIntegrationError("OpenBao secret field is empty or non-string")
        return value
