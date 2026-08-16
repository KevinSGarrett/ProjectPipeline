from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from project_pipeline.domain import (
    DiscoveryArtifactKind,
    GapCategory,
    GapSeverity,
    IntakeMode,
    ProjectGap,
    ProjectGapReport,
    ProjectIntakeRequest,
    ProjectProfile,
    ProjectProfileDetection,
    RepositoryDiscovery,
)


def _report(gaps: list[ProjectGap]) -> ProjectGapReport:
    ordered = tuple(
        sorted(
            gaps,
            key=lambda gap: (
                {
                    GapSeverity.CRITICAL: 0,
                    GapSeverity.HIGH: 1,
                    GapSeverity.MEDIUM: 2,
                    GapSeverity.LOW: 3,
                    GapSeverity.INFO: 4,
                }[gap.severity],
                gap.category.value,
                gap.gap_id,
            ),
        )
    )
    payload = json.dumps(
        [item.model_dump(mode="json") for item in ordered],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    fingerprint = __import__("hashlib").sha256(payload).hexdigest()
    counts = Counter(item.severity.value for item in ordered)
    return ProjectGapReport(
        gaps=ordered,
        counts_by_severity=dict(sorted(counts.items())),
        blocks_autonomy=any(item.blocks_autonomy for item in ordered),
        fingerprint=fingerprint,
    )


def analyze_project_gaps(
    request: ProjectIntakeRequest,
    discovery: RepositoryDiscovery,
    profile: ProjectProfileDetection,
) -> ProjectGapReport:
    paths = {item.path for item in discovery.files}
    lower_paths = {path.lower() for path in paths}
    roles = Counter(item.role for item in discovery.files)
    gaps: list[ProjectGap] = []

    if discovery.boundary_violations:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.BOUNDARY,
                severity=GapSeverity.CRITICAL,
                title="Repository boundary violations require operator review",
                description=(
                    "One or more symbolic links or nested repositories cross the configured "
                    "discovery boundary. Discovery did not traverse them."
                ),
                remediation=(
                    "Review each boundary reference, explicitly permit a nested repository only when "
                    "its authority is understood, and keep external targets outside autonomous mutation."
                ),
                affected_paths=tuple(discovery.boundary_violations),
                blocks_autonomy=True,
            )
        )

    secret_files = tuple(
        sorted(
            path
            for path in paths
            if Path(path).name.lower() in {".env", "credentials.json", "secrets.json", "id_rsa"}
        )
    )
    if secret_files:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.SECURITY,
                severity=GapSeverity.CRITICAL,
                title="Potential committed secret-bearing files detected",
                description=(
                    "The repository contains filenames commonly used for live credentials. File content "
                    "was not emitted into the report."
                ),
                remediation=(
                    "Quarantine and review the files, rotate any exposed credentials, replace values with "
                    "secret references, and preserve evidence before further automation."
                ),
                affected_paths=secret_files,
                blocks_autonomy=True,
            )
        )

    if "readme.md" not in lower_paths:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.DOCUMENTATION,
                severity=GapSeverity.MEDIUM,
                title="Repository overview is missing",
                description="No root README.md was discovered.",
                remediation="Create a concise repository overview with purpose, setup, validation, and ownership.",
                affected_paths=("README.md",),
                bootstrap_eligible=True,
            )
        )

    if not discovery.instruction_paths:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.INSTRUCTIONS,
                severity=GapSeverity.HIGH,
                title="Project instruction authority is missing",
                description=(
                    "No recognized instruction file or instruction directory was discovered. Autonomous "
                    "work cannot safely infer project-specific constraints from code alone."
                ),
                remediation=(
                    "Create an instruction authority that states repository boundaries, source hierarchy, "
                    "quality gates, prohibited operations, and escalation rules."
                ),
                affected_paths=("instruction/README.md",),
                blocks_autonomy=request.mode is IntakeMode.EXISTING_PROJECT,
                bootstrap_eligible=True,
            )
        )

    if not discovery.plan_paths:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.PLANNING,
                severity=GapSeverity.MEDIUM,
                title="Project plan corpus is missing",
                description="No recognized plan, specification, or architecture location was discovered.",
                remediation="Create a small indexed plan entry point before decomposing autonomous work.",
                affected_paths=("plan/README.md",),
                bootstrap_eligible=True,
            )
        )

    if not discovery.jira_paths:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.GOVERNANCE,
                severity=GapSeverity.MEDIUM,
                title="Local work-management authority is missing",
                description="No local Jira mirror or equivalent structured work catalog was discovered.",
                remediation="Create a local work-management entry point and define remote synchronization later.",
                affected_paths=("jira/README.md",),
                bootstrap_eligible=True,
            )
        )

    if not discovery.requirement_paths:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.REQUIREMENTS,
                severity=GapSeverity.HIGH,
                title="Machine-readable requirements are missing",
                description="No recognized requirement catalog was discovered.",
                remediation=(
                    "Compile source requirements into stable identifiers before autonomous planning or mutation."
                ),
                affected_paths=("plan/requirements/README.md",),
                blocks_autonomy=request.mode is IntakeMode.EXISTING_PROJECT,
                bootstrap_eligible=True,
            )
        )

    source_count = roles[DiscoveryArtifactKind.SOURCE]
    test_count = roles[DiscoveryArtifactKind.TEST]
    if source_count and not test_count:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.TESTING,
                severity=GapSeverity.HIGH,
                title="Source code has no discovered automated tests",
                description=f"The repository contains {source_count} source files and no recognized test files.",
                remediation="Add a profile-appropriate smoke test and the smallest meaningful unit-test slice.",
                affected_paths=("tests/",),
                blocks_autonomy=True,
                bootstrap_eligible=True,
            )
        )

    if source_count and roles[DiscoveryArtifactKind.CI] == 0:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.CI,
                severity=GapSeverity.MEDIUM,
                title="Continuous verification configuration is missing",
                description="Source code was discovered without a recognized CI workflow.",
                remediation="Add a least-privilege CI workflow after local commands are verified.",
                affected_paths=(".github/workflows/ci.yml",),
                bootstrap_eligible=True,
            )
        )

    if source_count and not discovery.build_systems:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.BUILD,
                severity=GapSeverity.HIGH,
                title="Build-system declaration is missing",
                description="Source files were discovered without recognized package or build metadata.",
                remediation="Declare the profile-appropriate build and dependency authority.",
                blocks_autonomy=True,
                bootstrap_eligible=True,
            )
        )

    if (
        "license" not in lower_paths
        and "license.md" not in lower_paths
        and "license.txt" not in lower_paths
    ):
        gaps.append(
            ProjectGap.create(
                category=GapCategory.GOVERNANCE,
                severity=GapSeverity.LOW,
                title="Repository license declaration is missing",
                description="No root license file was discovered.",
                remediation="Have the project owner select and approve a license; do not infer legal terms automatically.",
            )
        )

    if profile.primary_profile is ProjectProfile.EMPTY:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.PROFILE,
                severity=GapSeverity.INFO,
                title="Greenfield repository requires controlled bootstrap",
                description="The target has no discovered project files.",
                remediation="Apply an explicit profile-aware bootstrap plan; dry-run is the default.",
                bootstrap_eligible=True,
            )
        )

    if discovery.diagnostics:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.AUTHORITY,
                severity=GapSeverity.MEDIUM,
                title="Discovery diagnostics require review",
                description="One or more files could not be fully interpreted during read-only discovery.",
                remediation="Review diagnostics and repair malformed declarations before relying on them.",
                affected_paths=tuple(
                    sorted(
                        diagnostic.split(":", 1)[0]
                        for diagnostic in discovery.diagnostics
                        if ":" in diagnostic
                    )
                ),
                blocks_autonomy=any("not parseable" in item for item in discovery.diagnostics),
            )
        )

    if request.mode is IntakeMode.EXISTING_PROJECT:
        gaps.append(
            ProjectGap.create(
                category=GapCategory.AUTHORITY,
                severity=GapSeverity.INFO,
                title="Existing-project adoption remains non-destructive",
                description=(
                    "Discovery, baseline, gap analysis, and an adoption plan precede controlled bootstrap. "
                    "No existing files, workflows, branches, protections, Jira data, or directories may be "
                    "rewritten on first contact."
                ),
                remediation=(
                    "Require an explicit controlled-bootstrap action and preserve backup, impact, and rollback evidence."
                ),
            )
        )

    return _report(gaps)
