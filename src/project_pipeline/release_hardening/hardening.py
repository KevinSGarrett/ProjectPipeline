from __future__ import annotations

import json
import shutil
from pathlib import Path

from project_pipeline.release_hardening.models import (
    HardeningReport,
    PackagingTargetQualification,
    QualificationState,
    ToolQualification,
)
from project_pipeline.security.supply_chain import evaluate_supply_chain

PASS24_TOOLS = (
    ("UPSTREAM-007", "Trivy", "trivy", "security scanner"),
    ("UPSTREAM-043", "Gitleaks", "gitleaks", "secret scanner"),
    ("UPSTREAM-047", "OSV-Scanner", "osv-scanner", "dependency vulnerability scanner"),
    ("UPSTREAM-048", "k6", "k6", "performance/load generator"),
    ("UPSTREAM-053", "Infracost", "infracost", "IaC cost estimator"),
    ("UPSTREAM-069", "act", "act", "local GitHub Actions runner"),
    ("UPSTREAM-081", "OpenSSF Scorecard", "scorecard", "repository security evidence"),
    ("UPSTREAM-089", "Renovate", "renovate", "dependency update automation"),
    ("UPSTREAM-090", "restic", "restic", "backup mechanics"),
    ("UPSTREAM-094", "Cosign", "cosign", "signature verification"),
    ("UPSTREAM-100", "Harden-Runner", None, "CI runtime hardening profile"),
    ("UPSTREAM-114", "WinSW", "winsw", "Windows service supervision"),
)


def _registry(root: Path) -> dict[str, dict]:
    document = json.loads((root / "provenance/upstream_registry.json").read_text(encoding="utf-8"))
    return {item["upstream_id"]: item for item in document["entries"]}


def qualify_tools(root: Path) -> tuple[ToolQualification, ...]:
    registry = _registry(root)
    policy = json.loads((root / "config/release_policy.json").read_text(encoding="utf-8"))
    results = []
    for upstream_id, name, executable, role in PASS24_TOOLS:
        record = registry[upstream_id]
        license_value = str(record.get("license", "UNKNOWN"))
        available = bool(executable and shutil.which(executable))
        notes = []
        if upstream_id in policy["activation_blocked_upstream_ids"]:
            state = QualificationState.BLOCKED_LICENSE_POLICY
            notes.append("activation prohibited by current license policy")
        elif upstream_id == "UPSTREAM-100":
            workflow = (root / ".github/workflows/quality.yml").read_text(encoding="utf-8")
            pin = policy["harden_runner_reviewed_sha"]
            state = (
                QualificationState.CONFIGURED_PINNED_PROFILE
                if f"step-security/harden-runner@{pin}" in workflow
                else QualificationState.BLOCKED_EXTERNAL
            )
            notes.append(
                "CI configuration is source-qualified; hosted runner execution is separate"
            )
        elif available:
            state = QualificationState.AVAILABLE_NOT_EXECUTED
            notes.append(
                "binary is present; pass-level report does not infer a successful scan from presence"
            )
        else:
            state = QualificationState.ADAPTER_IMPLEMENTED_TOOL_UNAVAILABLE
            notes.append("runtime binary unavailable in the current environment")
        results.append(
            ToolQualification(
                upstream_id=upstream_id,
                tool=name,
                license=license_value,
                allowed_role=role,
                executable=executable,
                runtime_available=available,
                state=state,
                notes=tuple(notes),
            )
        )
    return tuple(results)


def qualify_packaging_targets(root: Path) -> tuple[PackagingTargetQualification, ...]:
    checks = (
        (
            "python_local",
            (root / "pyproject.toml").is_file(),
            bool(shutil.which("python") or shutil.which("python3")),
            "python -m project_pipeline validate --root .",
            (),
        ),
        (
            "windows_service",
            (root / "infrastructure/windows/ProjectPipelineService.xml").is_file(),
            bool(shutil.which("pwsh") and shutil.which("winsw")),
            "pwsh -File scripts/windows/verify.ps1",
            ("Windows and WinSW runtimes required",),
        ),
        (
            "windows_desktop",
            (root / "apps/desktop_shell/src-tauri/tauri.conf.json").is_file(),
            bool(shutil.which("cargo") and shutil.which("rustc")),
            "cargo tauri build",
            ("Rust/Cargo and Windows desktop target required",),
        ),
        (
            "docker",
            (root / "infrastructure/docker/Dockerfile").is_file(),
            bool(shutil.which("docker")),
            "docker build with PROJECT_PIPELINE_BASE_IMAGE set to an immutable digest",
            ("Docker runtime and approved immutable base image digest required",),
        ),
        (
            "aws_terraform",
            (root / "infrastructure/aws/terraform/main.tf").is_file(),
            bool(shutil.which("terraform")),
            "terraform init -backend=false && terraform validate",
            (
                "Terraform runtime and separately authorized AWS target required for live qualification",
            ),
        ),
    )
    rows = []
    for target, assets, runtime, command, blockers in checks:
        if target == "python_local" and assets and runtime:
            state = QualificationState.VERIFIED_LOCAL
        elif assets:
            state = QualificationState.SOURCE_IMPLEMENTED_RUNTIME_NOT_QUALIFIED
        else:
            state = QualificationState.BLOCKED_EXTERNAL
        rows.append(
            PackagingTargetQualification(
                target=target,
                source_assets_present=assets,
                runtime_available=runtime,
                state=state,
                verification_command=command,
                blockers=blockers if not runtime else (),
            )
        )
    return tuple(rows)


def build_hardening_report(root: Path) -> HardeningReport:
    gate, _ = evaluate_supply_chain(root)
    policy = json.loads((root / "config/dependency_policy.json").read_text(encoding="utf-8"))
    resolver = policy.get("resolver_lock", {})
    profiles = tuple(
        sorted(
            path.stem
            for path in (root / "config/runtime/profiles").glob("*.json")
            if path.stem
            in {"development", "test", "staging", "production", "recovery", "synthetic"}
        )
    )
    targets = qualify_packaging_targets(root)
    blockers = []
    if resolver.get("state") != "READY":
        blockers.append("resolver lock is not READY")
    blockers.append("independent Completion Gate has not declared the project complete")
    for row in targets:
        if row.target != "python_local" and row.state is not QualificationState.VERIFIED_LOCAL:
            blockers.append(f"{row.target} runtime qualification is incomplete")
    return HardeningReport(
        tool_qualifications=qualify_tools(root),
        packaging_targets=targets,
        environment_profiles=profiles,
        supply_chain_state=gate.state.value,
        resolver_lock_state=str(resolver.get("state", "UNKNOWN")),
        production_blockers=tuple(dict.fromkeys(blockers)),
    )
