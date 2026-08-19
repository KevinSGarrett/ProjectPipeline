from __future__ import annotations

import ast
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.command_center.models import HealthDimension
from project_pipeline.io import sha256_canonical_file
from project_pipeline.observability.logging import sanitize
from project_pipeline.observability.ops_health import calculate_health, health_dimensions
from project_pipeline.observability.ops_models import (
    DEFAULT_FRESHNESS_SECONDS,
    REDACTED_FIELDS,
    CacheEvent,
    CacheOutcome,
    CodeIndexEntry,
    CostSample,
    DependencyUpdateClass,
    DistilledMemory,
    HealthCalculation,
    HealthLayerObservation,
    WorkerRunRecord,
    canonical_digest,
    ops_identifier,
)
from project_pipeline.observability.ops_store import OpsIntelligenceStore


def _redact(value: Any) -> Any:
    return sanitize(value, REDACTED_FIELDS)


def record_layer(store: OpsIntelligenceStore, payload: dict[str, Any]) -> HealthLayerObservation:
    cleaned = _redact(payload)
    if not isinstance(cleaned, dict):
        raise ValueError("layer payload must be an object")
    observation = HealthLayerObservation.model_validate(cleaned)
    return store.put_layer(observation)


def record_worker(store: OpsIntelligenceStore, payload: dict[str, Any]) -> WorkerRunRecord:
    cleaned = _redact(payload)
    if not isinstance(cleaned, dict):
        raise ValueError("worker payload must be an object")
    record = WorkerRunRecord.model_validate(cleaned)
    return store.put_worker(record)


def record_cost(store: OpsIntelligenceStore, payload: dict[str, Any]) -> CostSample:
    cleaned = _redact(payload)
    if not isinstance(cleaned, dict):
        raise ValueError("cost payload must be an object")
    sample = CostSample.model_validate(cleaned)
    return store.put_cost(sample)


def record_cache(store: OpsIntelligenceStore, payload: dict[str, Any]) -> CacheEvent:
    cleaned = _redact(payload)
    if not isinstance(cleaned, dict):
        raise ValueError("cache payload must be an object")
    event = CacheEvent.model_validate(cleaned)
    return store.put_cache(event)


def distill_memory(store: OpsIntelligenceStore, payload: dict[str, Any]) -> DistilledMemory:
    if payload.get("conversation_history") or payload.get("chat"):
        raise ValueError("raw conversation history cannot become distilled project memory")
    cleaned = _redact(payload)
    if not isinstance(cleaned, dict):
        raise ValueError("memory payload must be an object")
    if not cleaned.get("citations"):
        raise ValueError("distilled memory requires citations")
    if cleaned.get("verified") is not True:
        raise ValueError("distilled memory must be verified structured truth")
    memory = DistilledMemory.model_validate(cleaned)
    return store.put_memory(memory)


def evaluate_health(
    store: OpsIntelligenceStore,
    *,
    as_of_utc: datetime | None = None,
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
) -> HealthCalculation:
    return calculate_health(store, as_of_utc=as_of_utc, freshness_seconds=freshness_seconds)


def cache_identity(cache_kind: str, artifact_digest: str, layer: str) -> str:
    return canonical_digest({"kind": cache_kind, "digest": artifact_digest, "layer": layer})


def record_cache_outcome(
    store: OpsIntelligenceStore,
    *,
    cache_kind: str,
    artifact_digest: str,
    layer: str,
    outcome: CacheOutcome,
    recorded_at_utc: datetime | None = None,
) -> CacheEvent:
    recorded = recorded_at_utc or datetime.now(UTC)
    identity = cache_identity(cache_kind, artifact_digest, layer)
    event = CacheEvent(
        event_id=ops_identifier("cache", identity, outcome.value, recorded.isoformat()),
        cache_kind=cache_kind,
        cache_identity=identity,
        outcome=outcome,
        recorded_at_utc=recorded,
    )
    return store.put_cache(event)


def _last_commit(root: Path, relative: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--format=%H", "--", relative],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    value = (completed.stdout or "").strip().lower()
    if completed.returncode != 0 or len(value) != 40:
        return None
    return value


def _python_symbols(source: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    tree = ast.parse(source)
    imports: list[str] = []
    symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            symbols.append(node.name)
    return tuple(sorted(set(imports))), tuple(sorted(set(symbols)))


def build_code_index(root: Path, *, limit: int = 400) -> list[CodeIndexEntry]:
    root = root.resolve()
    entries: list[CodeIndexEntry] = []
    roots = [root / "src" / "project_pipeline", root / "tests"]
    for base in roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if len(entries) >= limit:
                break
            relative = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
                imports, symbols = _python_symbols(text)
            except (OSError, SyntaxError, UnicodeError):
                continue
            test_ids = tuple(
                item for item in symbols if item.startswith("test_") or item.startswith("TEST-")
            )
            related = tuple(
                item
                for item in imports
                if item.startswith("project_pipeline") or item.startswith("tests")
            )
            entries.append(
                CodeIndexEntry(
                    path=relative,
                    file_sha256=sha256_canonical_file(path),
                    imports=imports,
                    symbols=symbols,
                    test_ids=test_ids,
                    last_commit_sha=_last_commit(root, relative),
                    related_paths=related,
                )
            )
        if len(entries) >= limit:
            break
    return entries


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in value.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def classify_dependency_updates(root: Path) -> list[DependencyUpdateClass]:
    root = root.resolve()
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    raw_project = document.get("project")
    project: dict[str, Any] = raw_project if isinstance(raw_project, dict) else {}
    raw_runtime = project.get("dependencies")
    runtime: list[Any] = raw_runtime if isinstance(raw_runtime, list) else []
    raw_optional = project.get("optional-dependencies")
    optional: dict[str, Any] = raw_optional if isinstance(raw_optional, dict) else {}
    rows: list[DependencyUpdateClass] = []
    runtime_names = set()
    for spec in runtime:
        if not isinstance(spec, str) or not spec.strip():
            continue
        name = spec.split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0].strip()
        runtime_names.add(name.casefold())
        rows.append(_classify_spec(name, spec, criticality="runtime"))
    for extra, specs in optional.items():
        if not isinstance(specs, list):
            continue
        for spec in specs:
            if not isinstance(spec, str) or not spec.strip():
                continue
            name = spec.split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0].strip()
            if name.casefold() in runtime_names:
                continue
            rows.append(_classify_spec(name, spec, criticality=f"optional:{extra}"))
    return rows


def _classify_spec(name: str, spec: str, *, criticality: str) -> DependencyUpdateClass:
    current = spec
    proposed = spec
    security = "LOW"
    lowered = f"{name} {spec}".casefold()
    if "security" in lowered or "cve" in lowered:
        security = "HIGH"
    compatibility = "LOW"
    versions = [
        item
        for item in spec.replace("=", " ").replace(">", " ").replace("<", " ").split()
        if any(ch.isdigit() for ch in item)
    ]
    if len(versions) >= 2:
        left = _version_tuple(versions[0])
        right = _version_tuple(versions[1])
        if left and right and left[0] != right[0]:
            compatibility = "HIGH"
        elif left and right and left != right:
            compatibility = "MEDIUM"
    verification = ["tests/test_ops_intelligence.py"]
    if security == "HIGH":
        verification.append("supply-chain")
    if criticality == "runtime":
        verification.append("repository-validate")
    return DependencyUpdateClass(
        package=name,
        current_version=current,
        proposed_version=proposed,
        security_urgency=security,
        compatibility_risk=compatibility,
        criticality=criticality,
        required_verification=tuple(verification),
        create_work=security == "HIGH" or compatibility == "HIGH",
    )


def load_ops_health_dimensions(root: Path | None) -> tuple[HealthDimension, ...]:
    if root is None:
        return ()
    database = root / ".local" / "state" / "ops_intelligence" / "ops.sqlite3"
    if not database.is_file():
        return ()
    store = OpsIntelligenceStore(database)
    try:
        return health_dimensions(calculate_health(store))
    finally:
        store.close()


def run_ops_action(
    root: Path,
    action: str,
    *,
    payload: dict[str, Any] | None = None,
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
) -> dict[str, Any]:
    store = OpsIntelligenceStore.open(root)
    try:
        if action == "health":
            calculation = evaluate_health(store, freshness_seconds=freshness_seconds)
            return calculation.model_dump(mode="json")
        if action == "status":
            calculation = evaluate_health(store, freshness_seconds=freshness_seconds)
            return {
                "health": calculation.model_dump(mode="json"),
                "worker_count": len(store.list_kind("worker")),
                "cost_count": len(store.list_kind("cost")),
                "cache_count": len(store.list_kind("cache")),
                "memory_count": len(store.list_kind("memory")),
                "user_action_required": False,
            }
        if action == "index":
            entries = [item.model_dump(mode="json") for item in build_code_index(root)]
            return {"entry_count": len(entries), "entries": entries}
        if action == "classify-deps":
            rows = classify_dependency_updates(root)
            return {
                "update_count": len(rows),
                "updates": [item.model_dump(mode="json") for item in rows],
            }
        if payload is None:
            raise ValueError(f"{action} requires a JSON payload")
        if action == "record-layer":
            return record_layer(store, payload).model_dump(mode="json")
        if action == "record-worker":
            return record_worker(store, payload).model_dump(mode="json")
        if action == "record-cost":
            return record_cost(store, payload).model_dump(mode="json")
        if action == "record-cache":
            return record_cache(store, payload).model_dump(mode="json")
        if action == "distill":
            return distill_memory(store, payload).model_dump(mode="json")
        raise ValueError(f"unsupported ops-intelligence action: {action}")
    finally:
        store.close()
