from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

_REQUIRED = (
    "config/release_policy.json",
    "config/pass24_hardening_matrix.json",
    "infrastructure/docker/Dockerfile",
    "infrastructure/docker/compose.yaml",
    "infrastructure/docker/README.md",
    "infrastructure/windows/ProjectPipelineService.xml",
    "infrastructure/windows/README.md",
    "scripts/windows/install.ps1",
    "scripts/windows/uninstall.ps1",
    "scripts/windows/upgrade.ps1",
    "scripts/windows/rollback.ps1",
    "scripts/windows/verify.ps1",
    "scripts/run_command_center_service.py",
    "scripts/run_pass24_hardening.py",
    "docs/operations/INSTALLATION_AND_OPERATIONS.md",
    "docs/development/DEVELOPER_GUIDE.md",
    "docs/api/API_REFERENCE.md",
    "docs/architecture/FINAL_ARCHITECTURE.md",
    "docs/release/RELEASE_PROCEDURE.md",
    "runbooks/release_upgrade_and_rollback.md",
    "release/release_candidate_r24.json",
    "release/hardening_report_r24.json",
    "release/sbom_r24.json",
    "provenance/pass_24_upstream_hardening_gate.json",
    "provenance/reviews/PASS-24_hardening_packaging_upstream_review.md",
)


def validate_release_hardening(root: Path) -> list[str]:
    errors = []
    for rel in _REQUIRED:
        if not (root / rel).is_file():
            errors.append(f"required Pass 24 artifact is missing: {rel}")
    if errors:
        return errors
    policy = json.loads((root / "config/release_policy.json").read_text(encoding="utf-8"))
    if set(policy.get("activation_blocked_upstream_ids", [])) != {"UPSTREAM-048", "UPSTREAM-089"}:
        errors.append("current license policy must block both k6 and Renovate activation")
    matrix = json.loads((root / "config/pass24_hardening_matrix.json").read_text(encoding="utf-8"))
    if len(matrix.get("tools", [])) != 12:
        errors.append("Pass 24 hardening matrix must cover exactly 12 gated upstream candidates")
    if any(
        item.get("authority") != "EVIDENCE_OR_MECHANICS_ONLY" for item in matrix.get("tools", [])
    ):
        errors.append("hardening tools may not become canonical policy or release authorities")
    candidate = json.loads(
        (root / "release/release_candidate_r24.json").read_text(encoding="utf-8")
    )
    if candidate.get("readiness") != "LOCAL_HARDENING_CANDIDATE_NOT_PRODUCTION_READY":
        errors.append("r24 candidate must not claim production readiness")
    if candidate.get("external_live_qualification_claimed") is not False:
        errors.append("r24 candidate must not claim live external qualification")
    docker = (root / "infrastructure/docker/Dockerfile").read_text(encoding="utf-8")
    if (
        "ARG PROJECT_PIPELINE_BASE_IMAGE" not in docker
        or "FROM ${PROJECT_PIPELINE_BASE_IMAGE}" not in docker
    ):
        errors.append("Dockerfile must require an explicit base-image reference")
    if "USER projectpipeline" not in docker:
        errors.append("Dockerfile must run the application as a non-root user")
    try:
        tree = ElementTree.parse(root / "infrastructure/windows/ProjectPipelineService.xml")
    except ElementTree.ParseError as exc:
        errors.append(f"WinSW service XML is invalid: {exc}")
    else:
        xml = ElementTree.tostring(tree.getroot(), encoding="unicode")
        if "onfailure" not in xml or "restart" not in xml:
            errors.append("WinSW service XML must define recovery restart behavior")
        if any(word in xml.lower() for word in ("api_token=", "password=", "secret=")):
            errors.append("WinSW service XML must not contain secret material")
    expected = {"development", "test", "staging", "production", "recovery", "synthetic"}
    profiles = {p.stem for p in (root / "config/runtime/profiles").glob("*.json")}
    if not expected <= profiles:
        errors.append("runtime profiles do not cover all required environment classes")
    gate = json.loads(
        (root / "provenance/pass_24_upstream_hardening_gate.json").read_text(encoding="utf-8")
    )
    if set(gate.get("candidate_upstream_ids", [])) != {
        f"UPSTREAM-{value:03d}" for value in (7, 43, 47, 48, 53, 69, 81, 89, 90, 94, 100, 114)
    }:
        errors.append("Pass 24 upstream hardening gate candidate set is incomplete")
    return errors
