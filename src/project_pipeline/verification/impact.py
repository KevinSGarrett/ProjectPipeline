from __future__ import annotations

from collections.abc import Iterable

from project_pipeline.domain.verification import (
    VerificationCategory,
    VerificationImpactSet,
    verification_identifier,
)


def _normalized_paths(paths: Iterable[str]) -> tuple[str, ...]:
    values: list[str] = []
    for raw in paths:
        value = str(raw).replace("\\", "/").strip().lstrip("./")
        if value and value not in values:
            values.append(value)
    return tuple(sorted(values))


def _categories_for_path(path: str) -> tuple[set[VerificationCategory], str]:
    categories: set[VerificationCategory] = set()
    reasons: list[str] = []
    if path.startswith(("contracts/", "schemas/", "database/migrations/", "config/")):
        categories.add(VerificationCategory.CONTRACT)
        reasons.append("contract/configuration compatibility")
    if path.startswith(
        (
            "src/project_pipeline/api/",
            "src/project_pipeline/agents/",
            "src/project_pipeline/agent_router/",
        )
    ):
        categories.update({VerificationCategory.API, VerificationCategory.INTEGRATION})
        reasons.append("public API/provider integration surface")
    if path.startswith(
        (
            "src/project_pipeline/orchestration/",
            "src/project_pipeline/scheduler/",
            "src/project_pipeline/budget/",
        )
    ):
        categories.update({VerificationCategory.INTEGRATION, VerificationCategory.FAULT})
        reasons.append("stateful control/resource behavior")
    if path.startswith(("src/project_pipeline/assurance/", "src/project_pipeline/verification/")):
        categories.update(
            {
                VerificationCategory.CONTRACT,
                VerificationCategory.GOLDEN_JOURNEY,
                VerificationCategory.POST_MERGE,
            }
        )
        reasons.append("assurance authority and release evidence")
    if path.startswith(("apps/", "ui/", "web/", "src/project_pipeline/command_center/")):
        categories.update(
            {
                VerificationCategory.END_TO_END,
                VerificationCategory.BROWSER,
                VerificationCategory.VISUAL,
                VerificationCategory.ACCESSIBILITY,
                VerificationCategory.PERFORMANCE,
            }
        )
        reasons.append("operator-facing behavior")
    if path.startswith("src/project_pipeline/"):
        categories.add(VerificationCategory.CONTRACT)
        if len(categories) == 1:
            categories.add(VerificationCategory.INTEGRATION)
            reasons.append("unclassified source impact fails safe")
    if not categories:
        categories.update({VerificationCategory.CONTRACT, VerificationCategory.POST_MERGE})
        reasons.append("unclassified repository impact fails safe")
    return categories, "; ".join(reasons)


def _categories_for_acceptance(methods: tuple[str, ...]) -> set[VerificationCategory]:
    result: set[VerificationCategory] = set()
    for method in methods:
        token = method.lower()
        if "api" in token or "contract" in token:
            result.add(
                VerificationCategory.API if "api" in token else VerificationCategory.CONTRACT
            )
        if "e2e" in token or "end-to-end" in token or "journey" in token:
            result.update({VerificationCategory.END_TO_END, VerificationCategory.GOLDEN_JOURNEY})
        if "browser" in token or "visual" in token:
            result.update({VerificationCategory.BROWSER, VerificationCategory.VISUAL})
        if "accessib" in token or "axe" in token:
            result.add(VerificationCategory.ACCESSIBILITY)
        if "performance" in token or "latency" in token or "load" in token:
            result.add(VerificationCategory.PERFORMANCE)
        if "fault" in token or "recovery" in token or "resilience" in token:
            result.add(VerificationCategory.FAULT)
        if "property" in token or "invariant" in token:
            result.add(VerificationCategory.PROPERTY)
        if "mutation" in token:
            result.add(VerificationCategory.MUTATION)
        if "adversarial" in token or "negative" in token or "security" in token:
            result.add(VerificationCategory.ADVERSARIAL)
    return result


def derive_test_impact(
    changed_paths: Iterable[str],
    *,
    dependency_paths: Iterable[str] = (),
    requirement_ids: Iterable[str] = (),
    risk: str = "MEDIUM",
    acceptance_methods: Iterable[str] = (),
    profile_categories: Iterable[VerificationCategory] = (),
) -> VerificationImpactSet:
    """Derive a deterministic verification set from change, dependency, profile, risk and acceptance context.

    Unknown change surfaces fail safe to broader contract/post-merge or contract/integration
    verification. High and critical risk always broaden verification rather than narrowing it.
    """

    risk_value = str(risk).strip().upper()
    if risk_value not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise ValueError(f"unsupported verification risk: {risk}")
    paths = _normalized_paths(changed_paths)
    dependencies = _normalized_paths(dependency_paths)
    requirements = tuple(
        sorted(dict.fromkeys(str(value).strip() for value in requirement_ids if str(value).strip()))
    )
    methods = tuple(
        sorted(
            dict.fromkeys(
                str(value).strip().lower() for value in acceptance_methods if str(value).strip()
            )
        )
    )
    profile = tuple(sorted(dict.fromkeys(profile_categories), key=lambda item: item.value))
    categories: set[VerificationCategory] = set(profile)
    rationale: list[str] = []

    if profile:
        rationale.append("project verification profile contributes mandatory categories")

    for path in paths:
        selected, reason = _categories_for_path(path)
        categories.update(selected)
        rationale.append(f"changed:{path}: {reason}")
    for path in dependencies:
        selected, reason = _categories_for_path(path)
        categories.update(selected)
        categories.add(VerificationCategory.INTEGRATION)
        rationale.append(
            f"dependency:{path}: {reason}; dependency effects require integration verification"
        )

    if requirements:
        categories.add(VerificationCategory.CONTRACT)
        rationale.append("requirement-linked change requires acceptance/contract verification")

    acceptance_categories = _categories_for_acceptance(methods)
    if acceptance_categories:
        categories.update(acceptance_categories)
        rationale.append("acceptance verification methods contribute required categories")

    if risk_value == "HIGH":
        categories.update({VerificationCategory.ADVERSARIAL, VerificationCategory.PROPERTY})
        rationale.append("HIGH risk broadens verification to adversarial and property checks")
    elif risk_value == "CRITICAL":
        categories.update(
            {
                VerificationCategory.ADVERSARIAL,
                VerificationCategory.PROPERTY,
                VerificationCategory.GOLDEN_JOURNEY,
                VerificationCategory.END_TO_END,
                VerificationCategory.FAULT,
            }
        )
        rationale.append(
            "CRITICAL risk requires adversarial, property, golden, end-to-end, and fault evidence"
        )

    if not categories:
        categories.update({VerificationCategory.CONTRACT, VerificationCategory.POST_MERGE})
        rationale.append("empty impact fails safe to contract and post-merge verification")

    ordered_categories = tuple(sorted(categories, key=lambda item: item.value))
    impact_id = verification_identifier(
        "VIMPACT",
        *paths,
        *dependencies,
        *requirements,
        risk_value,
        *methods,
        *(item.value for item in profile),
        *(item.value for item in ordered_categories),
    )
    return VerificationImpactSet(
        impact_id=impact_id,
        changed_paths=paths,
        dependency_paths=dependencies,
        requirement_ids=requirements,
        risk=risk_value,
        acceptance_methods=methods,
        profile_categories=profile,
        required_categories=ordered_categories,
        rationale=tuple(dict.fromkeys(rationale)),
    )
