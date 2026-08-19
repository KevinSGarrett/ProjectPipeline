from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.assurance.acceptance_scope import (
    acceptance_scope_fingerprint,
    prove_metadata_only_diff,
)
from project_pipeline.assurance.evidence import load_evidence
from project_pipeline.assurance.observation_store import EvidenceObservationStore
from project_pipeline.assurance.policy import AssurancePolicy
from project_pipeline.assurance.repository_identity import resolve_repository_identity
from project_pipeline.domain.evidence_observation import (
    EnvironmentClass,
    EvidenceObservation,
    MergeKind,
    ObservationResult,
    canonical_fingerprint,
    observation_identifier,
)
from project_pipeline.io import read_json, read_jsonl, sha256_canonical_file

TestRunner = Callable[[list[str], list[str]], dict[str, str]]
MOCK_ENVIRONMENTS = {"mock", "simulated", "fixture", "dry-run"}


def definition_rows(root: Path) -> list[dict[str, Any]]:
    return [dict(row) for row in load_evidence(root)]


def get_definition(root: Path, evidence_id: str) -> dict[str, Any] | None:
    for row in definition_rows(root):
        if str(row.get("evidence_id")) == evidence_id:
            return row
    return None


def classify_environment(value: str) -> EnvironmentClass:
    text = value.casefold()
    if any(token in text for token in MOCK_ENVIRONMENTS):
        return EnvironmentClass.MOCK
    if "live" in text:
        return EnvironmentClass.LIVE
    if "windows" in text:
        return EnvironmentClass.WINDOWS_NATIVE
    if "ci" in text or "github" in text:
        return EnvironmentClass.CI
    return EnvironmentClass.LOCAL


def observation_rejection(
    observation: EvidenceObservation | None,
    *,
    requirement_id: str,
    evidence_id: str,
    test_ids: list[str],
    current_sha: str | None,
    current_tree: str | None,
    acceptance_fingerprint: str,
    policy: AssurancePolicy,
    now: datetime,
    live_required: bool,
    definition: dict[str, Any] | None,
) -> str | None:
    if observation is None:
        return f"evidence {evidence_id} has no valid current-head observation"
    if observation.evidence_id != evidence_id:
        return f"observation {observation.observation_id} is bound to a different evidence id"
    if requirement_id not in observation.requirement_ids:
        return f"observation {observation.observation_id} is unbound from {requirement_id}"
    if live_required and observation.environment_class is EnvironmentClass.MOCK:
        return (
            f"observation {observation.observation_id} is mock-only and cannot prove live behavior"
        )
    if observation.verification_status != "VERIFIED":
        return f"observation {observation.observation_id} is not independently verified"
    outcomes = observation.test_outcomes
    if outcomes:
        for test_id in test_ids:
            outcome = outcomes.get(test_id)
            if outcome != "PASS":
                return (
                    f"observation {observation.observation_id} test {test_id} is "
                    f"{outcome or 'missing'}"
                )
    else:
        if observation.result is ObservationResult.FAIL:
            return f"observation {observation.observation_id} records FAIL"
        if observation.result is not ObservationResult.PASS:
            return f"observation {observation.observation_id} does not record PASS"
        missing_tests = [test_id for test_id in test_ids if test_id not in observation.test_ids]
        if missing_tests:
            return f"observation {observation.observation_id} is missing cataloged tests"
    age = max(0, int((now - observation.recorded_at_utc.astimezone(UTC)).total_seconds()))
    if age > policy.default_evidence_max_age_seconds:
        return f"observation {observation.observation_id} is stale"
    if not current_sha or not current_tree:
        return "current repository SHA/tree is required to prove current-head behavior"
    if observation.integrated_sha != current_sha:
        return f"observation {observation.observation_id} is bound to a different integrated SHA"
    if observation.integrated_tree != current_tree:
        return f"observation {observation.observation_id} is bound to a different integrated tree"
    if not _fingerprint_matches(observation, requirement_id, acceptance_fingerprint):
        return (
            f"observation {observation.observation_id} acceptance-scope fingerprint does not match"
        )
    if definition is not None:
        artifact = str(definition.get("artifact_path") or "")
        if artifact and observation.artifact_digest != str(definition.get("sha256") or ""):
            return f"observation {observation.observation_id} artifact digest does not match the definition"
    return None


def _fingerprint_matches(
    observation: EvidenceObservation, requirement_id: str, acceptance_fingerprint: str
) -> bool:
    scopes = observation.requirement_scope_fingerprints
    if scopes:
        return scopes.get(requirement_id) == acceptance_fingerprint
    return observation.acceptance_scope_fingerprint == acceptance_fingerprint


def select_current_observation(
    store: EvidenceObservationStore,
    evidence_id: str,
    *,
    current_sha: str,
    current_tree: str,
    acceptance_fingerprint: str,
    requirement_id: str | None = None,
) -> EvidenceObservation | None:
    exact = store.current(evidence_id, subject_sha=current_sha, subject_tree=current_tree)
    if exact is None:
        return None
    if requirement_id:
        return (
            exact if _fingerprint_matches(exact, requirement_id, acceptance_fingerprint) else None
        )
    if exact.acceptance_scope_fingerprint == acceptance_fingerprint:
        return exact
    if any(
        value == acceptance_fingerprint for value in exact.requirement_scope_fingerprints.values()
    ):
        return exact
    return None


def record_observation(
    store: EvidenceObservationStore,
    *,
    evidence_id: str,
    test_ids: Iterable[str],
    criterion_ids: Iterable[str],
    requirement_ids: Iterable[str],
    integrated_sha: str,
    integrated_tree: str,
    acceptance_scope_fingerprint: str,
    path_fingerprints: dict[str, str],
    artifact_digest: str,
    command_identity: Iterable[str],
    environment_class: EnvironmentClass,
    result: ObservationResult,
    verification_status: str = "VERIFIED",
    independent_verification_receipt: str = "",
    branch_head_sha: str | None = None,
    merge_kind: MergeKind = MergeKind.NONE,
    metadata_only_diff_proof: Any = None,
    now: datetime | None = None,
    requirement_scope_fingerprints: dict[str, str] | None = None,
    test_outcomes: dict[str, str] | None = None,
) -> EvidenceObservation:
    recorded = (now or datetime.now(UTC)).astimezone(UTC)
    previous = store.latest_any(evidence_id)
    observation = EvidenceObservation(
        observation_id=observation_identifier(
            evidence_id,
            integrated_sha,
            integrated_tree,
            acceptance_scope_fingerprint,
            result.value,
            recorded.isoformat(),
            "|".join(str(item) for item in command_identity) or "command",
        ),
        evidence_id=evidence_id,
        test_ids=tuple(test_ids),
        criterion_ids=tuple(criterion_ids),
        requirement_ids=tuple(requirement_ids),
        integrated_sha=integrated_sha,
        integrated_tree=integrated_tree,
        acceptance_scope_fingerprint=acceptance_scope_fingerprint,
        path_fingerprints=path_fingerprints,
        requirement_scope_fingerprints=dict(requirement_scope_fingerprints or {}),
        test_outcomes=dict(test_outcomes or {}),
        artifact_digest=artifact_digest,
        command_identity=tuple(command_identity),
        environment_class=environment_class,
        recorded_at_utc=recorded,
        result=result,
        verification_status=verification_status,  # type: ignore[arg-type]
        independent_verification_receipt=independent_verification_receipt,
        branch_head_sha=branch_head_sha,
        merge_kind=merge_kind,
        metadata_only_diff_proof=metadata_only_diff_proof,
        supersedes=previous.observation_id if previous else None,
        provenance=previous.observation_id if previous else None,
    )
    return store.put(observation)


def generate_observation(
    root: Path,
    evidence_id: str,
    *,
    store: EvidenceObservationStore | None = None,
    runner: TestRunner | None = None,
    now: datetime | None = None,
    current_sha: str | None = None,
    current_tree: str | None = None,
) -> EvidenceObservation:
    root = root.resolve()
    store = store or EvidenceObservationStore.open(root)
    definition = get_definition(root, evidence_id)
    if definition is None:
        raise ValueError(f"evidence definition is missing: {evidence_id}")
    sha, tree = current_sha, current_tree
    if not sha or not tree:
        sha, tree = resolve_repository_identity(root)
    requirements = {
        str(item.get("requirement_id")): item
        for item in read_jsonl(root / "plans/_traceability/requirements.jsonl")
    }
    requirement_ids = [str(item) for item in definition.get("requirement_ids") or ()]
    test_ids = [str(item) for item in definition.get("test_ids") or ()]
    if not test_ids:
        for requirement_id in requirement_ids:
            item = requirements.get(requirement_id) or {}
            test_ids.extend(str(test_id) for test_id in item.get("test_ids", []))
        test_ids = list(dict.fromkeys(test_ids))
    fingerprints: dict[str, str] = {}
    scope_map: dict[str, str] = {}
    for requirement_id in requirement_ids:
        item = requirements.get(requirement_id)
        if item is None:
            continue
        scope_map[requirement_id] = acceptance_scope_fingerprint(root, item)
        for relative in item.get("implementation_paths", []):
            path = root / str(relative)
            if path.is_file():
                fingerprints[str(relative).replace("\\", "/")] = sha256_canonical_file(path)
    if not scope_map:
        raise ValueError(f"evidence {evidence_id} is not linked to a requirement")
    pytest_ids = _pytest_test_ids(root, test_ids)
    node_ids = _node_test_ids(root, test_ids)
    catalog: list[str] = []
    results: dict[str, str] = {}
    if pytest_ids:
        catalog = _catalog_paths(root, pytest_ids)
        results.update((runner or _pytest_runner(root))(pytest_ids, catalog))
    node_catalog = _catalog_paths(root, node_ids) if node_ids else []
    if node_ids:
        results.update(_node_runner(root)(node_ids, node_catalog))
    test_outcomes = {test_id: "MISSING" for test_id in test_ids}
    test_outcomes.update({str(test_id): str(outcome) for test_id, outcome in results.items()})
    runnable = [*pytest_ids, *node_ids]
    failed = [test_id for test_id in runnable if test_outcomes.get(test_id) != "PASS"]
    result = ObservationResult.FAIL if failed or not runnable else ObservationResult.PASS
    artifact = str(definition.get("artifact_path") or "")
    digest = str(definition.get("sha256") or "")
    if artifact and (root / artifact).is_file():
        digest = sha256_canonical_file(root / artifact)
    combined = (
        next(iter(scope_map.values())) if len(scope_map) == 1 else canonical_fingerprint(scope_map)
    )
    return record_observation(
        store,
        evidence_id=evidence_id,
        test_ids=test_ids,
        criterion_ids=[str(item) for item in definition.get("criterion_ids") or ()],
        requirement_ids=requirement_ids,
        integrated_sha=sha,
        integrated_tree=tree,
        acceptance_scope_fingerprint=combined,
        path_fingerprints=fingerprints,
        requirement_scope_fingerprints=scope_map,
        test_outcomes=test_outcomes,
        artifact_digest=digest,
        command_identity=_command_identity(catalog, node_catalog, test_ids),
        environment_class=classify_environment(str(definition.get("environment") or "local")),
        result=result,
        independent_verification_receipt=_verification_receipt(pytest_ids, node_ids, test_ids),
        now=now,
    )


def refresh_post_merge_observations(
    root: Path,
    *,
    store: EvidenceObservationStore | None = None,
    current_sha: str | None = None,
    current_tree: str | None = None,
    previous_sha: str | None = None,
    previous_tree: str | None = None,
    merge_kind: MergeKind = MergeKind.SQUASH,
    now: datetime | None = None,
) -> list[EvidenceObservation]:
    """Rebind inherited observations after a proven metadata-only integration."""

    root = root.resolve()
    store = store or EvidenceObservationStore.open(root)
    sha, tree = current_sha, current_tree
    if not sha or not tree:
        sha, tree = resolve_repository_identity(root)
    refreshed: list[EvidenceObservation] = []
    requirements = list(read_jsonl(root / "plans/_traceability/requirements.jsonl"))
    by_id = {str(item.get("requirement_id")): item for item in requirements}
    for definition in definition_rows(root):
        evidence_id = str(definition.get("evidence_id"))
        inherited = store.latest_any(evidence_id)
        if inherited is None:
            continue
        if inherited.integrated_sha == sha and inherited.integrated_tree == tree:
            continue
        requirement_id = next(
            (item for item in inherited.requirement_ids if item in by_id),
            None,
        )
        if requirement_id is None:
            continue
        inherited_scopes = dict(inherited.requirement_scope_fingerprints)
        current_scopes = {
            req_id: acceptance_scope_fingerprint(root, by_id[req_id])
            for req_id in inherited.requirement_ids
            if req_id in by_id
        }
        if inherited_scopes:
            if any(
                current_scopes.get(req_id) != fingerprint
                for req_id, fingerprint in inherited_scopes.items()
            ):
                continue
            fingerprint = (
                next(iter(current_scopes.values()))
                if len(current_scopes) == 1
                else canonical_fingerprint(current_scopes)
            )
        else:
            fingerprint = acceptance_scope_fingerprint(root, by_id[requirement_id])
            if fingerprint != inherited.acceptance_scope_fingerprint:
                continue
            current_scopes = {requirement_id: fingerprint}
        prior_sha = previous_sha or inherited.integrated_sha
        prior_tree = previous_tree or inherited.integrated_tree
        proof = prove_metadata_only_diff(
            root,
            from_sha=prior_sha,
            to_sha=sha,
            from_tree=prior_tree,
            to_tree=tree,
            acceptance_scope_unchanged=True,
        )
        tree_equivalent = inherited.integrated_tree == tree
        if tree_equivalent and not proof.allowlisted:
            proof = proof.model_copy(
                update={"allowlisted": True, "reason": "proven identical integrated tree"}
            )
        if not proof.allowlisted:
            continue
        refreshed.append(
            record_observation(
                store,
                evidence_id=evidence_id,
                test_ids=inherited.test_ids,
                criterion_ids=inherited.criterion_ids,
                requirement_ids=inherited.requirement_ids,
                integrated_sha=sha,
                integrated_tree=tree,
                acceptance_scope_fingerprint=fingerprint,
                path_fingerprints=dict(inherited.path_fingerprints),
                requirement_scope_fingerprints=inherited_scopes or current_scopes,
                test_outcomes=dict(inherited.test_outcomes),
                artifact_digest=inherited.artifact_digest,
                command_identity=("evidence.refresh-post-merge", inherited.observation_id, sha),
                environment_class=inherited.environment_class,
                result=inherited.result,
                verification_status=inherited.verification_status,
                independent_verification_receipt=inherited.independent_verification_receipt,
                branch_head_sha=inherited.integrated_sha,
                merge_kind=merge_kind,
                metadata_only_diff_proof=proof,
                now=now,
            )
        )
    return refreshed


def evidence_status(
    root: Path,
    *,
    store: EvidenceObservationStore | None = None,
    current_sha: str | None = None,
    current_tree: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    store = store or EvidenceObservationStore.open(root)
    try:
        sha, tree = current_sha, current_tree
        if not sha or not tree:
            sha, tree = resolve_repository_identity(root)
    except ValueError:
        sha, tree = None, None
    rows = []
    for definition in definition_rows(root):
        evidence_id = str(definition.get("evidence_id"))
        current = (
            store.current(evidence_id, subject_sha=sha, subject_tree=tree) if sha and tree else None
        )
        rows.append(
            {
                "evidence_id": evidence_id,
                "definition_has_inline_subject": bool(
                    definition.get("integrated_sha")
                    or definition.get("head_sha")
                    or definition.get("integrated_tree")
                    or definition.get("tree_sha")
                ),
                "current_observation_id": None if current is None else current.observation_id,
                "current_result": None if current is None else current.result.value,
            }
        )
    return {
        "origin_sha": sha,
        "origin_tree": tree,
        "definitions": len(rows),
        "inline_subject_bindings": sum(1 for item in rows if item["definition_has_inline_subject"]),
        "current_observations": sum(1 for item in rows if item["current_observation_id"]),
        "store": store.status(),
        "rows": rows,
    }


def _pytest_test_ids(root: Path, test_ids: list[str]) -> list[str]:
    catalog = _test_catalog_map(root)
    selected: list[str] = []
    for test_id in test_ids:
        path = str((catalog.get(test_id) or {}).get("path") or "").replace("\\", "/")
        if path.endswith(".py"):
            selected.append(test_id)
    return selected


def _node_test_ids(root: Path, test_ids: list[str]) -> list[str]:
    catalog = _test_catalog_map(root)
    selected: list[str] = []
    for test_id in test_ids:
        path = str((catalog.get(test_id) or {}).get("path") or "").replace("\\", "/")
        if path.endswith(".mjs") or path.endswith(".js"):
            selected.append(test_id)
    return selected


def _command_identity(
    pytest_paths: list[str], node_paths: list[str], test_ids: list[str]
) -> tuple[str, ...]:
    parts: list[str] = []
    if pytest_paths:
        parts.extend(("pytest", *pytest_paths))
    if node_paths:
        parts.extend(("node", "--test", *node_paths))
    return tuple(parts) if parts else ("pytest", *test_ids)


def _verification_receipt(pytest_ids: list[str], node_ids: list[str], test_ids: list[str]) -> str:
    if pytest_ids and node_ids:
        return "local-pytest+node:" + ",".join(test_ids)
    if node_ids:
        return "local-node:" + ",".join(node_ids)
    return "local-pytest:" + ",".join(test_ids)


def _test_catalog_map(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "tests" / "TEST_CATALOG.json"
    if not path.is_file():
        return {}
    payload = read_json(path)
    return {
        str(item.get("test_id")): item
        for item in payload.get("tests", [])
        if isinstance(item, dict) and item.get("test_id")
    }


def _catalog_paths(root: Path, test_ids: list[str]) -> list[str]:
    catalog = _test_catalog_map(root)
    paths: list[str] = []
    for test_id in test_ids:
        entry = catalog.get(test_id)
        if entry and entry.get("path"):
            paths.append(str(entry["path"]))
    return list(dict.fromkeys(paths))


def _pytest_runner(root: Path) -> TestRunner:
    def run(test_ids: list[str], paths: list[str]) -> dict[str, str]:
        if not paths:
            return {test_id: "FAIL" for test_id in test_ids}
        completed = subprocess.run(
            ["pytest", "-q", *paths],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
        outcome = "PASS" if completed.returncode == 0 else "FAIL"
        return {test_id: outcome for test_id in test_ids}

    return run


def _parse_node_tap(text: str) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("ok ") and " - " in stripped:
            title = stripped.split(" - ", 1)[1].strip()
            outcomes[title] = "PASS"
        elif stripped.startswith("not ok ") and " - " in stripped:
            title = stripped.split(" - ", 1)[1].strip()
            outcomes[title] = "FAIL"
    return outcomes


def _node_runner(root: Path) -> TestRunner:
    def run(test_ids: list[str], paths: list[str]) -> dict[str, str]:
        catalog = _test_catalog_map(root)
        if not paths:
            return {test_id: "MISSING" for test_id in test_ids}
        node = "node"
        try:
            completed = subprocess.run(
                [node, "--test", "--test-reporter=tap", *paths],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
                shell=False,
            )
        except FileNotFoundError:
            return {test_id: "MISSING" for test_id in test_ids}
        if completed.returncode == 127 or (
            completed.returncode != 0 and not (completed.stdout or completed.stderr)
        ):
            return {test_id: "MISSING" for test_id in test_ids}
        parsed = _parse_node_tap(completed.stdout + "\n" + completed.stderr)
        results: dict[str, str] = {}
        for test_id in test_ids:
            title = str((catalog.get(test_id) or {}).get("callable") or "")
            results[test_id] = parsed.get(title, "MISSING")
        return results

    return run
