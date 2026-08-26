from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import tomllib
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from project_pipeline.io import write_json

_PROHIBITED_REFERENCE_MARKERS = ("git+", "http://", "https://", " @ ")
_LOCK_RELATIVE_PATH = "requirements/environment.lock.json"
_RUNTIME_EXPORT = "requirements/runtime.txt"
_DEVELOPMENT_EXPORT = "requirements/development.txt"
_QUALITY_EXPORT = "requirements/quality-tools.txt"


class DependencyError(RuntimeError):
    """Raised when dependency declarations or environment metadata are inconsistent."""


def normalized_name(value: str) -> str:
    return canonicalize_name(value)


def dependency_name(requirement: str) -> str:
    try:
        return normalized_name(Requirement(requirement).name)
    except Exception as error:
        raise ValueError(f"cannot parse dependency requirement: {requirement}") from error


def load_pyproject(root: Path) -> dict[str, Any]:
    with (root / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


def load_dependency_policy(root: Path) -> dict[str, Any]:
    path = root / "config" / "dependency_policy.json"
    if not path.is_file():
        raise DependencyError("dependency policy is missing: config/dependency_policy.json")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DependencyError(f"dependency policy is invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise DependencyError("dependency policy root must be an object")
    return document


def load_environment_lock(root: Path) -> dict[str, Any]:
    path = root / _LOCK_RELATIVE_PATH
    if not path.is_file():
        raise DependencyError(f"environment lock is missing: {_LOCK_RELATIVE_PATH}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DependencyError(f"environment lock is invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise DependencyError("environment lock root must be an object")
    return document


def direct_dependency_groups(root: Path) -> dict[str, list[str]]:
    document = load_pyproject(root)
    project = document.get("project", {})
    groups: dict[str, list[str]] = {"runtime": list(project.get("dependencies", []))}
    for name, values in sorted(project.get("optional-dependencies", {}).items()):
        groups[f"optional:{name}"] = list(values)
    for name, values in sorted(document.get("dependency-groups", {}).items()):
        string_values = [value for value in values if isinstance(value, str)]
        groups[f"group:{name}"] = string_values
    return groups


def _active_groups(root: Path) -> tuple[str, ...]:
    policy = load_dependency_policy(root)
    groups = policy.get("active_lock_groups")
    if (
        not isinstance(groups, list)
        or not groups
        or not all(isinstance(item, str) for item in groups)
    ):
        raise DependencyError(
            "dependency policy active_lock_groups must be a non-empty string list"
        )
    return tuple(groups)


def _distribution_index() -> dict[str, importlib.metadata.Distribution]:
    index: dict[str, importlib.metadata.Distribution] = {}
    for distribution in importlib.metadata.distributions():
        raw_name = distribution.metadata["Name"]
        if raw_name:
            index[normalized_name(raw_name)] = distribution
    return index


def _metadata_hash(distribution: importlib.metadata.Distribution) -> str:
    metadata_path = Path(distribution._path) / "METADATA"  # type: ignore[attr-defined]
    if not metadata_path.is_file():
        raise DependencyError(
            f"distribution metadata is missing for {distribution.metadata['Name']}"
        )
    return hashlib.sha256(metadata_path.read_bytes()).hexdigest()


def _license_metadata(distribution: importlib.metadata.Distribution) -> str:
    """Extract the reviewed license declaration that is bound by METADATA."""

    metadata = distribution.metadata
    for field in ("License-Expression", "License"):
        try:
            raw_value: object = metadata[field]
        except KeyError:
            continue
        if not isinstance(raw_value, str):
            continue
        value = raw_value.strip()
        if value and value.casefold() not in {"unknown", "none", "n/a"}:
            return value
    prefix = "License :: OSI Approved :: "
    for classifier in metadata.get_all("Classifier", ()):
        raw_classifier: object = classifier
        if isinstance(raw_classifier, str) and raw_classifier.startswith(prefix):
            value = raw_classifier.removeprefix(prefix).strip()
            if value:
                return value
    raise DependencyError(f"distribution license metadata is missing for {metadata['Name']}")


def _applicable_requirement(value: str) -> Requirement | None:
    requirement = Requirement(value)
    if requirement.marker is None:
        return requirement
    environment: dict[str, str] = {key: str(value) for key, value in default_environment().items()}
    environment["extra"] = ""
    return requirement if requirement.marker.evaluate(environment) else None


def _closure_for_direct_names(
    direct_names: set[str],
    distributions: dict[str, importlib.metadata.Distribution],
) -> set[str]:
    queue: deque[str] = deque(sorted(direct_names))
    closure: set[str] = set()
    while queue:
        name = queue.popleft()
        if name in closure:
            continue
        distribution = distributions.get(name)
        if distribution is None:
            raise DependencyError(
                f"active dependency is not installed in the observed environment: {name}"
            )
        closure.add(name)
        for raw in distribution.requires or ():
            requirement = _applicable_requirement(raw)
            if requirement is None:
                continue
            dependency = normalized_name(requirement.name)
            if dependency not in closure:
                queue.append(dependency)
    return closure


def _direct_names_by_group(root: Path, groups: tuple[str, ...]) -> dict[str, set[str]]:
    declarations = direct_dependency_groups(root)
    missing = sorted(set(groups) - set(declarations))
    if missing:
        raise DependencyError(f"active dependency groups are not declared: {', '.join(missing)}")
    return {
        group: {dependency_name(requirement) for requirement in declarations[group]}
        for group in groups
    }


def build_environment_lock(root: Path) -> dict[str, Any]:
    root = root.resolve()
    active_groups = _active_groups(root)
    direct_by_group = _direct_names_by_group(root, active_groups)
    distributions = _distribution_index()
    closure_by_group = {
        group: _closure_for_direct_names(names, distributions)
        for group, names in direct_by_group.items()
    }
    all_names = sorted({name for values in closure_by_group.values() for name in values})
    direct_memberships: dict[str, list[str]] = defaultdict(list)
    closure_memberships: dict[str, list[str]] = defaultdict(list)
    for group, names in direct_by_group.items():
        for name in names:
            direct_memberships[name].append(group)
    for group, names in closure_by_group.items():
        for name in names:
            closure_memberships[name].append(group)

    packages: list[dict[str, Any]] = []
    for name in all_names:
        distribution = distributions[name]
        applicable_requirements: list[str] = []
        for raw in distribution.requires or ():
            requirement = _applicable_requirement(raw)
            if requirement is not None:
                applicable_requirements.append(str(requirement))
        packages.append(
            {
                "name": name,
                "version": distribution.version,
                "metadata_sha256": _metadata_hash(distribution),
                "direct_groups": sorted(direct_memberships.get(name, [])),
                "closure_groups": sorted(closure_memberships.get(name, [])),
                "requires_dist": sorted(applicable_requirements, key=str.lower),
            }
        )

    document = {
        "schema_version": "1.0.0",
        "lock_kind": "OBSERVED_ENVIRONMENT",
        "reproducibility_scope": "Exact versions and installed metadata for active dependency groups",
        "resolver_lock_state": load_dependency_policy(root)
        .get("resolver_lock", {})
        .get("state", "UNKNOWN"),
        "python": {
            "implementation": default_environment()["implementation_name"],
            "version": default_environment()["python_full_version"],
            "platform_system": default_environment()["platform_system"],
            "platform_machine": default_environment()["platform_machine"],
        },
        "active_groups": list(active_groups),
        "direct_dependencies": {
            group: sorted(names) for group, names in sorted(direct_by_group.items())
        },
        "closure": {group: sorted(names) for group, names in sorted(closure_by_group.items())},
        "package_count": len(packages),
        "packages": packages,
        "licenses": {name: _license_metadata(distributions[name]) for name in all_names},
    }
    write_json(root / _LOCK_RELATIVE_PATH, document)
    _write_portable_exports(root, document)
    return document


def _locked_package_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    packages = document.get("packages", [])
    if not isinstance(packages, list):
        raise DependencyError("environment lock packages must be a list")
    for item in packages:
        if not isinstance(item, dict):
            raise DependencyError("environment lock contains a non-object package record")
        name = item.get("name")
        version = item.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise DependencyError("environment lock package records require name and version")
        normalized = normalized_name(name)
        if normalized in result:
            raise DependencyError(f"environment lock contains duplicate package: {normalized}")
        result[normalized] = item
    return result


def locked_packages(root: Path) -> dict[str, str]:
    document = load_environment_lock(root)
    return {
        name: str(item["version"]) for name, item in sorted(_locked_package_map(document).items())
    }


def _render_export(document: dict[str, Any], groups: tuple[str, ...]) -> str:
    package_map = _locked_package_map(document)
    closure = document.get("closure", {})
    names: set[str] = set()
    for group in groups:
        values = closure.get(group, [])
        if not isinstance(values, list):
            raise DependencyError(f"environment lock closure for {group} must be a list")
        names.update(str(value) for value in values)
    header = [
        "# Generated from requirements/environment.lock.json.",
        "# Exact package versions are environment-observed; wheel hashes require resolver access.",
    ]
    rows = [f"{name}=={package_map[name]['version']}" for name in sorted(names)]
    return "\n".join([*header, *rows, ""])


def _render_quality_export(policy: dict[str, Any]) -> str:
    tools = policy.get("quality_tool_intents", [])
    lines = [
        "# Exact direct quality-tool intents; transitive resolver lock is externally blocked.",
        "# Generate uv.lock and replace this export when package-index access is available.",
    ]
    for item in tools if isinstance(tools, list) else []:
        if isinstance(item, dict) and isinstance(item.get("requirement"), str):
            lines.append(item["requirement"])
    return "\n".join([*lines, ""])


def _write_portable_exports(root: Path, document: dict[str, Any]) -> None:
    runtime_groups = ("runtime",)
    development_groups = tuple(document.get("active_groups", []))
    (root / _RUNTIME_EXPORT).write_text(
        _render_export(document, runtime_groups), encoding="utf-8", newline="\n"
    )
    (root / _DEVELOPMENT_EXPORT).write_text(
        _render_export(document, development_groups), encoding="utf-8", newline="\n"
    )
    policy = load_dependency_policy(root)
    (root / _QUALITY_EXPORT).write_text(
        _render_quality_export(policy), encoding="utf-8", newline="\n"
    )


def _validate_direct_requirements(
    root: Path,
    document: dict[str, Any],
    errors: list[str],
) -> None:
    groups = direct_dependency_groups(root)
    active_groups = _active_groups(root)
    package_map = _locked_package_map(document)
    for group in active_groups:
        for raw in groups[group]:
            lowered = raw.lower()
            if any(marker in lowered for marker in _PROHIBITED_REFERENCE_MARKERS):
                errors.append(f"{group} contains a prohibited direct reference: {raw}")
                continue
            requirement = Requirement(raw)
            name = normalized_name(requirement.name)
            item = package_map.get(name)
            if item is None:
                errors.append(f"{group} dependency is absent from environment lock: {name}")
                continue
            version = Version(str(item["version"]))
            if requirement.specifier and version not in requirement.specifier:
                errors.append(
                    f"{group} locked version violates declaration: {name}=={version} not in {requirement.specifier}"
                )


def validate_dependency_lock(root: Path, *, verify_installed: bool = False) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    try:
        policy = load_dependency_policy(root)
        document = load_environment_lock(root)
        package_map = _locked_package_map(document)
        _validate_direct_requirements(root, document, errors)
    except (DependencyError, OSError, ValueError, tomllib.TOMLDecodeError) as error:
        return [str(error)]

    declarations = direct_dependency_groups(root)
    declared_quality = declarations.get("group:quality", [])
    intents = policy.get("quality_tool_intents", [])
    governed_quality = [
        item["requirement"]
        for item in intents
        if isinstance(intents, list)
        if isinstance(item, dict) and isinstance(item.get("requirement"), str)
    ]
    if declared_quality != governed_quality:
        errors.append("pyproject quality group differs from dependency policy intents")

    if document.get("schema_version") != "1.0.0":
        errors.append("environment lock schema_version must be 1.0.0")
    if document.get("lock_kind") != "OBSERVED_ENVIRONMENT":
        errors.append("environment lock kind must be OBSERVED_ENVIRONMENT")
    if document.get("active_groups") != list(_active_groups(root)):
        errors.append("environment lock active_groups differ from dependency policy")
    if document.get("package_count") != len(package_map):
        errors.append("environment lock package_count is stale")
    licenses = document.get("licenses")
    if not isinstance(licenses, dict):
        errors.append("environment lock licenses must be an object")
    elif set(licenses) != set(package_map):
        errors.append("environment lock licenses must cover exactly the locked packages")
    else:
        for name, license_value in licenses.items():
            if not isinstance(license_value, str) or not license_value.strip():
                errors.append(f"environment lock license is missing: {name}")
    for name, item in package_map.items():
        digest = item.get("metadata_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"environment lock metadata hash is invalid: {name}")

    expected_exports = {
        _RUNTIME_EXPORT: _render_export(document, ("runtime",)),
        _DEVELOPMENT_EXPORT: _render_export(document, tuple(document.get("active_groups", []))),
    }
    for relative, expected in expected_exports.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"portable dependency export is missing: {relative}")
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(f"portable dependency export is stale: {relative}")
    quality_path = root / _QUALITY_EXPORT
    expected_quality = _render_quality_export(policy)
    if not quality_path.is_file():
        errors.append(f"quality-tool intent export is missing: {_QUALITY_EXPORT}")
    elif quality_path.read_text(encoding="utf-8") != expected_quality:
        errors.append(f"quality-tool intent export is stale: {_QUALITY_EXPORT}")

    resolver = policy.get("resolver_lock", {})
    if not isinstance(resolver, dict) or resolver.get("manager") != "uv":
        errors.append("dependency policy must define the uv resolver lock")
    else:
        state = resolver.get("state")
        if state not in {"READY", "BLOCKED_EXTERNAL"}:
            errors.append("resolver lock state must be READY or BLOCKED_EXTERNAL")
        if state == "READY" and not (root / "uv.lock").is_file():
            errors.append("resolver lock is READY but uv.lock is missing")
        if state == "BLOCKED_EXTERNAL" and not resolver.get("blocker"):
            errors.append("blocked resolver lock must record a blocker")

    if verify_installed:
        distributions = _distribution_index()
        observed = document.get("python", {})
        current = default_environment()
        current_version = current["python_full_version"].split(".")[:2]
        observed_version = str(observed.get("version", "")).split(".")[:2]
        same_environment = (
            observed.get("implementation") == current["implementation_name"]
            and observed.get("platform_system") == current["platform_system"]
            and observed.get("platform_machine") == current["platform_machine"]
            and observed_version == current_version
        )
        if same_environment:
            verification_names = set(package_map)
        else:
            direct_by_group = _direct_names_by_group(root, tuple(document.get("active_groups", [])))
            verification_names = {name for names in direct_by_group.values() for name in names}
        for name in sorted(verification_names):
            item = package_map[name]
            distribution = distributions.get(name)
            if distribution is None:
                errors.append(f"locked package is not installed: {name}")
                continue
            if distribution.version != item["version"]:
                errors.append(
                    f"installed version differs from environment lock: {name} "
                    f"{distribution.version} != {item['version']}"
                )
            elif same_environment and _metadata_hash(distribution) != item["metadata_sha256"]:
                errors.append(f"installed metadata differs from environment lock: {name}")
            elif same_environment and (
                not isinstance(licenses, dict)
                or licenses.get(name) != _license_metadata(distribution)
            ):
                errors.append(f"installed license metadata differs from environment lock: {name}")
    return errors


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    name: str
    group: str
    locked_version: str | None
    installed_version: str | None
    available: bool
    activation_state: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def dependency_status(root: Path) -> tuple[DependencyStatus, ...]:
    locked = locked_packages(root) if (root / _LOCK_RELATIVE_PATH).exists() else {}
    active = set(_active_groups(root))
    rows: list[DependencyStatus] = []
    for group, requirements in direct_dependency_groups(root).items():
        for raw in requirements:
            name = dependency_name(raw)
            try:
                installed = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                installed = None
            rows.append(
                DependencyStatus(
                    name=name,
                    group=group,
                    locked_version=locked.get(name),
                    installed_version=installed,
                    available=installed is not None,
                    activation_state="ACTIVE" if group in active else "DECLARED_NOT_ACTIVATED",
                )
            )
    return tuple(sorted(rows, key=lambda item: (item.group, item.name)))


def dependency_snapshot(root: Path) -> dict[str, Any]:
    policy = load_dependency_policy(root)
    document = load_environment_lock(root)
    groups = direct_dependency_groups(root)
    direct = {
        group: [dependency_name(requirement) for requirement in requirements]
        for group, requirements in groups.items()
    }
    return {
        "schema_version": "1.0.0",
        "requires_python": load_pyproject(root).get("project", {}).get("requires-python"),
        "direct_dependency_groups": direct,
        "direct_dependency_count": len({name for values in direct.values() for name in values}),
        "active_lock_groups": document.get("active_groups", []),
        "locked_package_count": document.get("package_count", 0),
        "lockfile": _LOCK_RELATIVE_PATH,
        "lock_kind": document.get("lock_kind"),
        "resolver_lock": policy.get("resolver_lock"),
        "portable_exports": [_RUNTIME_EXPORT, _DEVELOPMENT_EXPORT, _QUALITY_EXPORT],
    }


def write_dependency_snapshot(root: Path) -> dict[str, Any]:
    snapshot = dependency_snapshot(root)
    write_json(root / "provenance" / "dependency_snapshot.json", snapshot)
    return snapshot


def write_dependency_status(root: Path, output: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "errors": validate_dependency_lock(root),
        "dependencies": [item.as_dict() for item in dependency_status(root)],
    }
    result["ok"] = not result["errors"]
    write_json(output, result)
    return result
