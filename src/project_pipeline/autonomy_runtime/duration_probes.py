"""Read-only, evidence-bearing probes for a running qualification window.

The campaign controller owns cadence, receipts, and failure disposition.  This
module deliberately owns only bounded observations; it never changes GitHub or
Jira and it never mutates the candidate worktree.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from project_pipeline.autonomy_runtime.campaign import inspect_worktree_identity

_REQUIRED_PROBE_IDS = frozenset(
    {
        "candidate_identity",
        "runtime_doctor",
        "repository_validate",
        "jira_validate",
        "control_evaluate",
        "control_sequence",
        "command_center_projection",
        "autonomy_director_restart",
        "desktop_artifact_health",
        "cursor_cli_provider_dispatch",
        "github_live_readback",
        "jira_live_readback",
        "campaign_persistence_integrity",
        "recovery_isolation",
    }
)


def required_probe_ids() -> frozenset[str]:
    """Return the complete production duration-probe surface."""

    return _REQUIRED_PROBE_IDS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("candidate evidence must be a JSON object")
    return payload


def _candidate_evidence(
    path: Path | None, *, expected_sha: str, expected_tree: str
) -> tuple[bool, dict[str, Any]]:
    if path is None or not path.is_file():
        return False, {"reason": "candidate-evidence-missing"}
    try:
        payload = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return False, {"reason": "candidate-evidence-invalid", "error": type(error).__name__}
    identity_ok = (
        payload.get("integrated_sha") == expected_sha
        and payload.get("integrated_tree") == expected_tree
    )
    return identity_ok, {
        "path": str(path),
        "sha256": _sha256(path),
        "identity_ok": identity_ok,
        "payload": payload,
    }


def _subject(root: Path) -> dict[str, Any]:
    identity = inspect_worktree_identity(root)
    return {
        "sha": identity.get("sha"),
        "tree": identity.get("tree"),
        "clean": not bool(identity.get("dirty")),
        "inspect_ok": bool(identity.get("ok")),
    }


def _require_external_worker_root(repository_root: Path, path: Path, *, label: str) -> Path:
    """Reject probe state nested below the immutable candidate checkout."""

    resolved = path.resolve()
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be outside the immutable candidate checkout")


def _default_duration_probe_root() -> Path:
    """Allocate an external, worker-local root for an ad-hoc duration probe."""

    return (
        Path(tempfile.gettempdir()) / f"projectpipeline-duration-probes-{uuid4().hex}"
    ).resolve()


def _probe_command_center(root: Path) -> dict[str, Any]:
    from project_pipeline.command_center.application_validation import (
        validate_command_center_application,
    )
    from project_pipeline.command_center.validation import validate_command_center_foundation

    foundation_errors = validate_command_center_foundation(root)
    application_errors = validate_command_center_application(root)
    return {
        "foundation_errors": foundation_errors,
        "application_errors": application_errors,
        "projection_truthful": not foundation_errors and not application_errors,
    }


def _probe_director_restart(root: Path, state_root: Path) -> dict[str, Any]:
    from project_pipeline.command_center.autonomy_director import (
        PersistentAutonomyDirector,
        evaluate_live_control,
    )

    state_root.mkdir(parents=True, exist_ok=True)
    control = evaluate_live_control(root, database_path=state_root / "control.sqlite3")
    state_path = state_root / "director-state.json"
    director = PersistentAutonomyDirector(state_path)
    decision = director.select_next_work(control)
    recovered = PersistentAutonomyDirector(state_path).recover()
    projection = PersistentAutonomyDirector(state_path).projection()
    return {
        "decision_id": decision.decision_id,
        "selected_task_id": decision.selected_task_id,
        "control_snapshot_id": control.snapshot_id,
        "recovered": recovered.get("recovered") is True,
        "readmission_required": recovered.get("readmission_required") is True,
        "persisted_decision_count": int(projection.get("decision_count") or 0),
    }


def _probe_artifacts(
    candidate: dict[str, Any], *, expected_sha: str, expected_tree: str
) -> dict[str, Any]:
    payload = candidate.get("payload")
    if not isinstance(payload, dict) or not candidate.get("identity_ok"):
        return {"ok": False, "reason": "candidate-evidence-identity-mismatch"}
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return {"ok": False, "reason": "candidate-artifacts-missing"}
    rows: list[dict[str, Any]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            return {"ok": False, "reason": "candidate-artifact-malformed"}
        path = Path(str(item.get("path") or ""))
        expected_digest = str(item.get("sha256") or "")
        if not path.is_file() or len(expected_digest) != 64:
            return {"ok": False, "reason": "candidate-artifact-unavailable"}
        actual = _sha256(path)
        rows.append(
            {
                "name": str(item.get("name") or path.name),
                "path": str(path),
                "sha256": actual,
                "matches": actual == expected_digest,
            }
        )
    lifecycle = payload.get("remote_lifecycle")
    checks = lifecycle.get("checks") if isinstance(lifecycle, dict) else None
    lifecycle_ok = (
        isinstance(lifecycle, dict)
        and lifecycle.get("state") == "VERIFIED"
        and lifecycle.get("source") == "REMOTE_DRAFT_BYTES"
        and lifecycle.get("worktree_bytes_used") is False
        and lifecycle.get("execution_mode") == "REAL_NATIVE_REMOTE_BYTES"
        and isinstance(checks, dict)
        and bool(checks)
        and all(str(value).startswith("PASS") for value in checks.values())
    )
    return {
        "ok": all(row["matches"] for row in rows) and lifecycle_ok,
        "artifacts": rows,
        "remote_lifecycle_verified": lifecycle_ok,
        "integrated_sha": expected_sha,
        "integrated_tree": expected_tree,
    }


def _run_json(argv: list[str], *, cwd: Path, timeout_seconds: float = 45.0) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        shell=False,
    )
    text = (completed.stdout or "").strip()
    try:
        payload = json.loads(text) if text else None
    except json.JSONDecodeError:
        payload = None
    return {
        "exit_code": completed.returncode,
        "payload": payload,
        "stderr_class": None if not completed.stderr else "command-stderr",
    }


def _probe_cursor(root: Path, state_root: Path) -> dict[str, Any]:
    from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
        qualify_cursor_cli_provider,
    )

    workspace = state_root / "cursor-disposable"
    report = qualify_cursor_cli_provider(
        repository_root=root,
        disposable_root=workspace,
    )
    return {
        "outcome": report.get("outcome"),
        "provider_id": report.get("provider_id"),
        "live_dispatch": report.get("live_dispatch"),
        "replay_verified": report.get("replay_verified"),
        "reasons": report.get("reasons") or [],
    }


def verify_remote_candidate(
    root: Path,
    candidate: dict[str, Any],
    *,
    expected_sha: str,
) -> dict[str, Any]:
    """Read and hash the real GitHub draft assets bound to a candidate."""

    from project_pipeline.autonomy_runtime.live_qualification import (
        _DEFAULT_REPOSITORY_SLUG,
        _github_repository_slug_from_url,
        _resolve_github_token,
    )
    from project_pipeline.github_steward.adapter import GitHubRestAdapter

    project = _read_json(root / "config" / "project.json")
    repository = str(project.get("repository") or "")
    slug = _github_repository_slug_from_url(repository) or _DEFAULT_REPOSITORY_SLUG
    if "/" not in slug:
        return {"ok": False, "reason": "repository-slug-unavailable"}
    raw_candidate_payload = candidate.get("payload")
    candidate_payload: dict[str, Any] = (
        raw_candidate_payload if isinstance(raw_candidate_payload, dict) else {}
    )
    release = candidate_payload.get("draft_release")
    artifacts = candidate_payload.get("artifacts")
    if not isinstance(release, dict) or not isinstance(artifacts, list) or not artifacts:
        return {"ok": False, "reason": "candidate-draft-or-artifacts-missing"}
    try:
        release_id = int(release["release_id"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "reason": "candidate-release-id-invalid"}
    expected_assets = {
        str(item.get("name")): str(item.get("sha256"))
        for item in artifacts
        if isinstance(item, dict) and item.get("name") and item.get("sha256")
    }
    if len(expected_assets) != len(artifacts):
        return {"ok": False, "reason": "candidate-artifact-manifest-invalid"}
    token, token_source = _resolve_github_token(root)
    if not token:
        return {"ok": False, "reason": "github-token-unavailable"}
    remote: Any | None = None
    try:
        remote = GitHubRestAdapter(token=token)
        snapshot = remote.get_release(slug, release_id)
        main = next((item for item in remote.iter_branches(slug) if item.name == "main"), None)
        if snapshot is None:
            return {
                "ok": False,
                "reason": "draft-release-unavailable",
                "provider": remote.provider_id,
            }
        observed = {asset.name: asset for asset in snapshot.assets}
        hashes = {
            name: hashlib.sha256(
                remote.download_release_asset(slug, asset_id=asset.api_id)
            ).hexdigest()
            for name, asset in observed.items()
        }
    except Exception as error:
        return {"ok": False, "reason": type(error).__name__}
    finally:
        if remote is not None:
            remote.discard_secret_material()
        token = ""
    assets_ok = set(observed) == set(expected_assets) and hashes == expected_assets
    return {
        "ok": bool(candidate.get("identity_ok"))
        and snapshot.draft
        and snapshot.target_commitish.lower() == expected_sha.lower()
        and main is not None
        and main.sha.lower() == expected_sha.lower()
        and assets_ok,
        "provider": remote.provider_id,
        "token_source": token_source,
        "main_sha": None if main is None else main.sha,
        "release": {
            "available": True,
            "release_id": snapshot.api_id,
            "draft": snapshot.draft,
            "target_commitish": snapshot.target_commitish,
            "asset_hashes": hashes,
            "assets_match": assets_ok,
        },
    }


def _probe_github(root: Path, candidate: dict[str, Any], expected_sha: str) -> dict[str, Any]:
    return verify_remote_candidate(root, candidate, expected_sha=expected_sha)


def _probe_jira(root: Path) -> dict[str, Any]:
    from project_pipeline.autonomy_runtime.live_qualification import _build_jira_adapter

    adapter: Any | None = None
    try:
        adapter = _build_jira_adapter(root)
        desired = {"PP-384", "PP-385", "PP-391", "PP-393"}
        observed: dict[str, str] = {}
        for key in sorted(desired):
            issue = adapter.get_issue(key)
            if issue is not None:
                observed[key] = str(issue.status_name)
        return {"ok": set(observed) == desired, "issues": observed}
    except Exception as error:
        return {"ok": False, "reason": type(error).__name__}
    finally:
        discard = getattr(adapter, "discard_secret_material", None)
        if callable(discard):
            discard()


def _validate_campaign_event_chain(connection: sqlite3.Connection, campaign_id: str) -> bool:
    previous: str | None = None
    rows = connection.execute(
        """
        SELECT action, status, payload_json, prev_event_sha256, event_sha256, created_at_utc
        FROM campaign_events WHERE campaign_id = ? ORDER BY rowid
        """,
        (campaign_id,),
    ).fetchall()
    if not rows:
        return False
    for action, status, raw_payload, previous_hash, event_hash, created_at in rows:
        if previous_hash != previous or not event_hash:
            return False
        payload = json.loads(str(raw_payload))
        body = {
            "campaign_id": campaign_id,
            "action": str(action),
            "status": str(status),
            "payload": payload,
            "prev_event_sha256": previous,
            "created_at_utc": str(created_at),
        }
        computed = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if computed != str(event_hash):
            return False
        previous = computed
    row = connection.execute(
        "SELECT last_event_sha256 FROM campaign_runs WHERE campaign_id = ?", (campaign_id,)
    ).fetchone()
    return row is not None and previous == row[0]


def _probe_campaign_database(
    database: Path | None, campaign_id: str | None, expected_sha: str, expected_tree: str
) -> dict[str, Any]:
    if database is None or campaign_id is None or not database.is_file():
        return {"ok": False, "reason": "campaign-database-missing"}
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        row = connection.execute(
            """
            SELECT integrated_sha, integrated_tree, fence, qualification_run_id, status
            FROM campaign_runs WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchone()
        return {
            "ok": bool(row)
            and integrity.lower() == "ok"
            and str(row[0]) == expected_sha
            and str(row[1]) == expected_tree
            and bool(row[2])
            and bool(row[3])
            and _validate_campaign_event_chain(connection, campaign_id),
            "integrity": integrity,
            "campaign_status": None if row is None else str(row[4]),
            "event_chain_valid": False
            if row is None
            else _validate_campaign_event_chain(connection, campaign_id),
        }
    finally:
        connection.close()


def _probe_recovery_isolation(database: Path | None, campaign_id: str | None) -> dict[str, Any]:
    if database is None or campaign_id is None or not database.is_file():
        return {"ok": False, "reason": "campaign-database-missing"}
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        campaign_locks = connection.execute(
            "SELECT campaign_id, process_id FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchall()
        qualification_locks = connection.execute(
            "SELECT run_id, process_id FROM qualification_locks WHERE lock_name = 'active-qualification'"
        ).fetchall()
        row = connection.execute(
            "SELECT qualification_run_id FROM campaign_runs WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        expected_run = None if row is None else str(row[0] or "")
        return {
            "ok": len(campaign_locks) == 1
            and str(campaign_locks[0][0]) == campaign_id
            and len(qualification_locks) == 1
            and str(qualification_locks[0][0]) == expected_run
            and int(campaign_locks[0][1]) > 0
            and int(qualification_locks[0][1]) > 0,
            "campaign_lock_count": len(campaign_locks),
            "qualification_lock_count": len(qualification_locks),
            "expected_run_id": expected_run,
        }
    finally:
        connection.close()


def run_duration_probe(
    probe_id: str,
    *,
    repository_root: Path,
    expected_sha: str,
    expected_tree: str,
    campaign_database: Path | None = None,
    campaign_id: str | None = None,
    candidate_evidence: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Run one bounded observation and return a content-addressed result."""

    root = repository_root.resolve()
    probe_state = _require_external_worker_root(
        root,
        state_root or _default_duration_probe_root(),
        label="state_root",
    )
    subject = _subject(root)
    identity_ok = (
        subject["inspect_ok"]
        and subject["clean"]
        and subject["sha"] == expected_sha
        and subject["tree"] == expected_tree
    )
    candidate_ok, candidate = _candidate_evidence(
        candidate_evidence, expected_sha=expected_sha, expected_tree=expected_tree
    )
    observations: dict[str, Any]
    try:
        if probe_id == "candidate_identity":
            observations = {"identity_ok": identity_ok, "candidate_evidence_ok": candidate_ok}
            ok = identity_ok and candidate_ok
        elif probe_id == "command_center_projection":
            observations = _probe_command_center(root)
            ok = identity_ok and bool(observations["projection_truthful"])
        elif probe_id == "autonomy_director_restart":
            observations = _probe_director_restart(root, probe_state / "director")
            ok = (
                identity_ok
                and observations["recovered"]
                and observations["persisted_decision_count"] > 0
            )
        elif probe_id == "desktop_artifact_health":
            observations = _probe_artifacts(
                candidate, expected_sha=expected_sha, expected_tree=expected_tree
            )
            ok = identity_ok and bool(observations["ok"])
        elif probe_id == "cursor_cli_provider_dispatch":
            observations = _probe_cursor(root, probe_state)
            ok = identity_ok and observations.get("outcome") == "PASSED"
        elif probe_id == "github_live_readback":
            observations = _probe_github(root, candidate, expected_sha)
            ok = identity_ok and bool(observations["ok"])
        elif probe_id == "jira_live_readback":
            observations = _probe_jira(root)
            ok = identity_ok and bool(observations["ok"])
        elif probe_id == "campaign_persistence_integrity":
            observations = _probe_campaign_database(
                campaign_database, campaign_id, expected_sha, expected_tree
            )
            ok = identity_ok and bool(observations["ok"])
        elif probe_id == "recovery_isolation":
            observations = _probe_recovery_isolation(campaign_database, campaign_id)
            ok = identity_ok and bool(observations["ok"])
        else:
            return {
                "ok": False,
                "probe_id": probe_id,
                "subject": subject,
                "reason": "unknown-probe-id",
            }
    except Exception as error:
        observations = {"error": type(error).__name__}
        ok = False

    payload = {
        "schema_version": "1.0.0",
        "probe_id": probe_id,
        "ok": bool(ok),
        "subject": subject,
        "expected_sha": expected_sha,
        "expected_tree": expected_tree,
        "candidate_evidence_sha256": candidate.get("sha256"),
        "observations": observations,
    }
    payload["evidence_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload
