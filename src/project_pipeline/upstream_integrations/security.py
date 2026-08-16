from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from project_pipeline.upstream_integrations.common import (
    CommandOutcome,
    CommandPlan,
    Runner,
    confined,
    default_runner,
    executable_available,
    execute_plan,
    require_safe_value,
)


@dataclass(slots=True)
class GitleaksAdapter:
    executable: str = "gitleaks"
    runner: Runner = default_runner
    timeout_seconds: float = 300.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_git_scan(self, root: Path, report: Path) -> CommandPlan:
        root = root.resolve()
        report_path = confined(root, report)
        return CommandPlan(
            upstream_id="UPSTREAM-043",
            argv=(
                self.executable,
                "git",
                "--no-banner",
                "--redact=100",
                "--report-format",
                "json",
                "--report-path",
                str(report_path),
                str(root),
            ),
            cwd=str(root),
            output_format="text",
            evidence_sources=("gitleaks/gitleaks:README.md",),
            metadata={"report_path": str(report_path)},
        )

    def execute(self, plan: CommandPlan) -> CommandOutcome:
        return execute_plan(plan, runner=self.runner, timeout_seconds=self.timeout_seconds)


@dataclass(slots=True)
class OsvScannerAdapter:
    executable: str = "osv-scanner"
    runner: Runner = default_runner
    timeout_seconds: float = 600.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_source_scan(
        self, root: Path, *, recursive: bool = True, offline: bool = False
    ) -> CommandPlan:
        root = root.resolve()
        argv = [self.executable]
        if offline:
            argv.append("--offline")
        argv.extend(["scan", "source", "--format", "json"])
        if recursive:
            argv.append("-r")
        argv.append(str(root))
        return CommandPlan(
            upstream_id="UPSTREAM-047",
            argv=tuple(argv),
            cwd=str(root),
            network_required=not offline,
            output_format="json",
            evidence_sources=(
                "google/osv-scanner:README.md",
                "google/osv-scanner:docs/output.md",
                "google/osv-scanner:LICENSE",
            ),
        )

    def execute(self, plan: CommandPlan, *, allow_network: bool = False) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
        )


@dataclass(slots=True)
class CosignVerifyAdapter:
    executable: str = "cosign"
    runner: Runner = default_runner
    timeout_seconds: float = 300.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_verify(
        self,
        root: Path,
        image_digest_ref: str,
        *,
        certificate_identity: str | None = None,
        certificate_oidc_issuer: str | None = None,
        key: Path | None = None,
    ) -> CommandPlan:
        root = root.resolve()
        require_safe_value(image_digest_ref, field_name="image_digest_ref")
        if "@sha256:" not in image_digest_ref:
            raise ValueError("cosign verification requires an immutable @sha256 digest reference")
        argv = [self.executable, "verify"]
        if key is not None:
            key_path = confined(root, key, must_exist=True)
            argv.extend(["--key", str(key_path)])
        else:
            if not certificate_identity or not certificate_oidc_issuer:
                raise ValueError(
                    "certificate identity and OIDC issuer are required for keyless verification"
                )
            argv.extend(["--certificate-identity", certificate_identity])
            argv.extend(["--certificate-oidc-issuer", certificate_oidc_issuer])
        argv.append(image_digest_ref)
        return CommandPlan(
            upstream_id="UPSTREAM-094",
            argv=tuple(argv),
            cwd=str(root),
            network_required=True,
            output_format="text",
            evidence_sources=("sigstore/cosign:README.md",),
        )

    def execute(self, plan: CommandPlan, *, allow_network: bool = False) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
        )


@dataclass(slots=True)
class ZizmorAdapter:
    executable: str = "zizmor"
    runner: Runner = default_runner
    timeout_seconds: float = 300.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_offline_audit(self, root: Path) -> CommandPlan:
        root = root.resolve()
        return CommandPlan(
            upstream_id="UPSTREAM-116",
            argv=(
                self.executable,
                "--offline",
                "--strict-collection",
                "--format=json-v1",
                str(root),
            ),
            cwd=str(root),
            network_required=False,
            output_format="json",
            evidence_sources=(
                "zizmorcore/zizmor:README.md",
                "zizmorcore/zizmor:docs/usage.md",
            ),
        )

    def execute(self, plan: CommandPlan) -> CommandOutcome:
        return execute_plan(plan, runner=self.runner, timeout_seconds=self.timeout_seconds)


@dataclass(slots=True)
class TrivyAdapter:
    executable: str = "trivy"
    runner: Runner = default_runner
    timeout_seconds: float = 900.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_filesystem_scan(
        self,
        root: Path,
        *,
        scanners: tuple[str, ...] = ("vuln", "secret", "misconfig"),
        offline: bool = False,
    ) -> CommandPlan:
        root = root.resolve()
        allowed = {"vuln", "secret", "misconfig", "license"}
        if not scanners or any(item not in allowed for item in scanners):
            raise ValueError("unsupported Trivy scanner set")
        argv = [
            self.executable,
            "filesystem",
            "--format",
            "json",
            "--scanners",
            ",".join(scanners),
            "--disable-telemetry",
            "--no-progress",
        ]
        if offline:
            argv.extend(
                [
                    "--offline-scan",
                    "--skip-db-update",
                    "--skip-java-db-update",
                    "--skip-check-update",
                ]
            )
        argv.append(str(root))
        return CommandPlan(
            upstream_id="UPSTREAM-007",
            argv=tuple(argv),
            cwd=str(root),
            network_required=not offline,
            output_format="json",
            evidence_sources=(
                "aquasecurity/trivy:docs/guide/references/configuration/cli/trivy_filesystem.md",
                "aquasecurity/trivy:pkg/types/report.go",
            ),
            metadata={"scanners": scanners, "offline": offline},
        )

    def plan_sbom(
        self, root: Path, *, format: str = "cyclonedx", offline: bool = False
    ) -> CommandPlan:
        root = root.resolve()
        if format not in {"cyclonedx", "spdx", "spdx-json"}:
            raise ValueError("unsupported Trivy SBOM format")
        argv = [
            self.executable,
            "filesystem",
            "--format",
            format,
            "--disable-telemetry",
            "--no-progress",
        ]
        if offline:
            argv.extend(
                [
                    "--offline-scan",
                    "--skip-db-update",
                    "--skip-java-db-update",
                    "--skip-check-update",
                ]
            )
        argv.append(str(root))
        return CommandPlan(
            upstream_id="UPSTREAM-007",
            argv=tuple(argv),
            cwd=str(root),
            network_required=not offline,
            output_format="json" if format in {"cyclonedx", "spdx-json"} else "text",
            evidence_sources=(
                "aquasecurity/trivy:docs/guide/references/configuration/cli/trivy_filesystem.md",
            ),
            metadata={"sbom_format": format, "offline": offline},
        )

    def execute(self, plan: CommandPlan, *, allow_network: bool = False) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
        )


@dataclass(slots=True)
class OpaAdapter:
    executable: str = "opa"
    runner: Runner = default_runner
    timeout_seconds: float = 120.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_eval(
        self, root: Path, *, policy_dir: Path, query: str, input_document: Mapping[str, object]
    ) -> CommandPlan:
        root = root.resolve()
        policy = confined(root, policy_dir, must_exist=True)
        require_safe_value(query, field_name="query")
        import json

        return CommandPlan(
            upstream_id="UPSTREAM-079",
            argv=(
                self.executable,
                "eval",
                "--format",
                "json",
                "--data",
                str(policy),
                "--stdin-input",
                query,
            ),
            cwd=str(root),
            stdin=json.dumps(input_document, sort_keys=True, separators=(",", ":")),
            output_format="json",
            evidence_sources=(
                "open-policy-agent/opa:docs/docs/policy-language.md",
                "open-policy-agent/opa:docs/docs/rest-api.md",
            ),
        )

    def execute(self, plan: CommandPlan) -> CommandOutcome:
        return execute_plan(plan, runner=self.runner, timeout_seconds=self.timeout_seconds)


@dataclass(slots=True)
class ConftestAdapter:
    executable: str = "conftest"
    runner: Runner = default_runner
    timeout_seconds: float = 120.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_test(self, root: Path, *, target: Path, policy_dir: Path) -> CommandPlan:
        root = root.resolve()
        target_path = confined(root, target, must_exist=True)
        policy = confined(root, policy_dir, must_exist=True)
        return CommandPlan(
            upstream_id="UPSTREAM-078",
            argv=(
                self.executable,
                "test",
                "--output",
                "json",
                "--policy",
                str(policy),
                str(target_path),
            ),
            cwd=str(root),
            output_format="json",
            evidence_sources=(
                "open-policy-agent/conftest:policy/engine.go",
                "open-policy-agent/conftest:output/result.go",
            ),
        )

    def execute(self, plan: CommandPlan) -> CommandOutcome:
        return execute_plan(plan, runner=self.runner, timeout_seconds=self.timeout_seconds)


@dataclass(slots=True)
class ScorecardAdapter:
    executable: str = "scorecard"
    runner: Runner = default_runner
    timeout_seconds: float = 300.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_repository_scan(self, root: Path, repository_url: str) -> CommandPlan:
        root = root.resolve()
        require_safe_value(repository_url, field_name="repository_url")
        if not repository_url.startswith("https://github.com/"):
            raise ValueError("Scorecard repository URL must be an HTTPS GitHub URL")
        return CommandPlan(
            upstream_id="UPSTREAM-081",
            argv=(self.executable, "--repo", repository_url, "--format", "json"),
            cwd=str(root),
            network_required=True,
            output_format="json",
            evidence_sources=("ossf/scorecard:docs/checks.md",),
        )

    def execute(self, plan: CommandPlan, *, allow_network: bool = False) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
        )


@dataclass(slots=True)
class SopsAdapter:
    executable: str = "sops"
    runner: Runner = default_runner
    timeout_seconds: float = 120.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_decrypt(
        self, root: Path, encrypted_file: Path, *, extract_expression: str | None = None
    ) -> CommandPlan:
        root = root.resolve()
        encrypted = confined(root, encrypted_file, must_exist=True)
        argv = [self.executable, "decrypt"]
        if extract_expression:
            require_safe_value(extract_expression, field_name="extract_expression")
            argv.extend(["--extract", extract_expression])
        argv.append(str(encrypted))
        return CommandPlan(
            upstream_id="UPSTREAM-039",
            argv=tuple(argv),
            cwd=str(root),
            output_format="secret-plaintext-runtime-only",
            evidence_sources=("getsops/sops:cmd/sops/main.go",),
            metadata={"plaintext_persistence_allowed": False},
        )


@dataclass(slots=True)
class AgeAdapter:
    executable: str = "age"
    runner: Runner = default_runner
    timeout_seconds: float = 120.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_decrypt(self, root: Path, encrypted_file: Path, *, identity_file: Path) -> CommandPlan:
        root = root.resolve()
        encrypted = confined(root, encrypted_file, must_exist=True)
        identity = identity_file.resolve()
        if not identity.exists() or identity.is_dir():
            raise ValueError("age identity file is unavailable")
        return CommandPlan(
            upstream_id="UPSTREAM-035",
            argv=(self.executable, "--decrypt", "--identity", str(identity), str(encrypted)),
            cwd=str(root),
            output_format="secret-plaintext-runtime-only",
            evidence_sources=("FiloSottile/age:age.go",),
            metadata={"identity_path_redacted": True, "plaintext_persistence_allowed": False},
        )
