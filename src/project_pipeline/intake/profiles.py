from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from project_pipeline.domain import (
    DiscoveredFile,
    DiscoveryArtifactKind,
    ProjectIntakeRequest,
    ProjectProfile,
    ProjectProfileDetection,
    RepositoryDiscovery,
)

_PROFILE_POLICIES: dict[ProjectProfile, tuple[str, ...]] = {
    ProjectProfile.GENERIC: (
        "source_control_integrity",
        "deterministic_validation",
        "evidence_capture",
    ),
    ProjectProfile.PYTHON_LIBRARY: (
        "python_lint",
        "python_type_check",
        "python_unit_tests",
        "package_build_validation",
    ),
    ProjectProfile.PYTHON_SERVICE: (
        "python_lint",
        "python_type_check",
        "python_unit_tests",
        "api_contract_tests",
        "service_smoke_test",
    ),
    ProjectProfile.WEB_APPLICATION: (
        "frontend_lint",
        "frontend_unit_tests",
        "browser_testing",
        "accessibility_testing",
        "api_testing",
        "build_validation",
    ),
    ProjectProfile.TYPESCRIPT_APPLICATION: (
        "typescript_lint",
        "typescript_type_check",
        "typescript_unit_tests",
        "build_validation",
    ),
    ProjectProfile.RUST_APPLICATION: (
        "rust_format_check",
        "rust_lint",
        "rust_unit_tests",
        "release_build_validation",
    ),
    ProjectProfile.MACHINE_LEARNING: (
        "data_lineage",
        "dataset_versioning",
        "reproducibility",
        "model_evaluation",
        "leakage_tests",
        "checkpoint_handling",
        "gpu_reservation",
        "experiment_tracking",
    ),
    ProjectProfile.INFRASTRUCTURE: (
        "infrastructure_static_validation",
        "policy_evaluation",
        "cost_preflight",
        "deployment_plan_review",
        "rollback_evidence",
    ),
    ProjectProfile.DOCUMENTATION: (
        "link_validation",
        "documentation_structure",
        "terminology_validation",
    ),
    ProjectProfile.POLYGLOT_APPLICATION: (
        "per_language_quality_gates",
        "cross_component_contract_tests",
        "build_order_validation",
    ),
    ProjectProfile.EMPTY: (
        "controlled_bootstrap",
        "project_manifest_required",
    ),
}


def _evidence_paths(
    discovery: RepositoryDiscovery, predicate: Callable[[DiscoveredFile], bool]
) -> tuple[str, ...]:
    return tuple(sorted(item.path for item in discovery.files if predicate(item)))


def detect_project_profile(
    discovery: RepositoryDiscovery, request: ProjectIntakeRequest
) -> ProjectProfileDetection:
    paths = {item.path for item in discovery.files}
    lower_paths = {path.lower() for path in paths}
    languages = Counter(item.language for item in discovery.files if item.language)
    profiles: set[ProjectProfile] = set(request.requested_profiles)
    evidence: dict[str, tuple[str, ...]] = {}

    python_markers = _evidence_paths(
        discovery,
        lambda item: (
            item.language == "Python"
            or item.path in {"pyproject.toml", "setup.py", "setup.cfg"}
            or item.path.startswith("requirements")
        ),
    )
    if python_markers:
        service_markers = _evidence_paths(
            discovery,
            lambda item: (
                item.language == "Python"
                and any(
                    token in item.path.lower()
                    for token in ("api", "app", "server", "service", "worker", "main")
                )
            ),
        )
        dependency_text = " ".join(
            dependency.lower() for item in discovery.files for dependency in item.dependencies
        )
        if service_markers or any(
            framework in dependency_text for framework in ("fastapi", "flask", "django", "uvicorn")
        ):
            profiles.add(ProjectProfile.PYTHON_SERVICE)
            evidence[ProjectProfile.PYTHON_SERVICE.value] = tuple(
                sorted(set(python_markers + service_markers))
            )
        else:
            profiles.add(ProjectProfile.PYTHON_LIBRARY)
            evidence[ProjectProfile.PYTHON_LIBRARY.value] = python_markers

    node_markers = tuple(
        sorted(
            path
            for path in paths
            if path == "package.json" or Path(path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}
        )
    )
    if node_markers:
        web_markers = tuple(
            sorted(
                path
                for path in paths
                if Path(path).suffix.lower() in {".html", ".css", ".scss", ".jsx", ".tsx"}
                or any(
                    token in path.lower() for token in ("frontend", "web", "pages", "components")
                )
            )
        )
        if web_markers:
            profiles.add(ProjectProfile.WEB_APPLICATION)
            evidence[ProjectProfile.WEB_APPLICATION.value] = tuple(
                sorted(set(node_markers + web_markers))
            )
        else:
            profiles.add(ProjectProfile.TYPESCRIPT_APPLICATION)
            evidence[ProjectProfile.TYPESCRIPT_APPLICATION.value] = node_markers

    rust_markers = tuple(
        sorted(path for path in paths if path == "Cargo.toml" or Path(path).suffix.lower() == ".rs")
    )
    if rust_markers:
        profiles.add(ProjectProfile.RUST_APPLICATION)
        evidence[ProjectProfile.RUST_APPLICATION.value] = rust_markers

    ml_markers = tuple(
        sorted(
            path
            for path in paths
            if Path(path).suffix.lower() in {".ipynb", ".onnx", ".pt", ".pth", ".safetensors"}
            or any(
                token in path.lower()
                for token in ("model", "dataset", "training", "experiment", "notebook")
            )
        )
    )
    if ml_markers:
        profiles.add(ProjectProfile.MACHINE_LEARNING)
        evidence[ProjectProfile.MACHINE_LEARNING.value] = ml_markers

    infrastructure_markers = tuple(
        sorted(
            path
            for path in paths
            if Path(path).suffix.lower() == ".tf"
            or any(
                path.lower().startswith(prefix)
                for prefix in ("infra/", "terraform/", "k8s/", "kubernetes/", "deploy/")
            )
            or Path(path).name.lower() in {"dockerfile", "compose.yml", "compose.yaml"}
        )
    )
    if infrastructure_markers:
        profiles.add(ProjectProfile.INFRASTRUCTURE)
        evidence[ProjectProfile.INFRASTRUCTURE.value] = infrastructure_markers

    code_file_count = sum(
        1
        for item in discovery.files
        if item.role is DiscoveryArtifactKind.SOURCE and item.language is not None
    )
    documentation_paths = tuple(
        sorted(
            item.path
            for item in discovery.files
            if item.role is DiscoveryArtifactKind.DOCUMENTATION
        )
    )
    if code_file_count == 0 and documentation_paths:
        profiles.add(ProjectProfile.DOCUMENTATION)
        evidence[ProjectProfile.DOCUMENTATION.value] = documentation_paths

    if not discovery.files:
        profiles.add(ProjectProfile.EMPTY)
        evidence[ProjectProfile.EMPTY.value] = ()

    language_families = {language for language, count in languages.items() if count > 0}
    if len(language_families) > 1:
        profiles.add(ProjectProfile.POLYGLOT_APPLICATION)
        evidence[ProjectProfile.POLYGLOT_APPLICATION.value] = tuple(
            sorted(item.path for item in discovery.files if item.language)
        )

    if not profiles:
        profiles.add(ProjectProfile.GENERIC)
        evidence[ProjectProfile.GENERIC.value] = tuple(sorted(lower_paths))[:20]

    precedence = (
        ProjectProfile.POLYGLOT_APPLICATION,
        ProjectProfile.MACHINE_LEARNING,
        ProjectProfile.WEB_APPLICATION,
        ProjectProfile.PYTHON_SERVICE,
        ProjectProfile.TYPESCRIPT_APPLICATION,
        ProjectProfile.RUST_APPLICATION,
        ProjectProfile.PYTHON_LIBRARY,
        ProjectProfile.INFRASTRUCTURE,
        ProjectProfile.DOCUMENTATION,
        ProjectProfile.EMPTY,
        ProjectProfile.GENERIC,
    )
    primary = next(profile for profile in precedence if profile in profiles)
    ordered_profiles = tuple(profile for profile in precedence if profile in profiles)
    confidence = (
        1.0
        if request.requested_profiles
        else min(0.98, 0.45 + 0.08 * max(1, len(evidence.get(primary.value, ()))))
    )
    policy_activations = tuple(
        sorted(
            {
                policy
                for profile in ordered_profiles
                for policy in _PROFILE_POLICIES.get(profile, ())
            }
        )
    )
    return ProjectProfileDetection(
        primary_profile=primary,
        profiles=ordered_profiles,
        confidence=confidence,
        evidence={key: tuple(sorted(value)) for key, value in sorted(evidence.items())},
        policy_activations=policy_activations,
    )
