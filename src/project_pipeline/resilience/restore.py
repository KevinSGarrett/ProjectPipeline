from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

WINDOWS = os.name == "nt"
PROTECTED_WINDOWS_PREFIXES = (
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\programdata",
    "c:\\system volume information",
    "c:\\$recycle.bin",
)
PROTECTED_POSIX_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/proc", "/sys", "/dev")
RESTORE_STATES = (
    "INTENT_RECORDED",
    "DRY_RUN_COMPLETE",
    "APPLIED",
    "VERIFIED",
    "FAILED",
    "UNKNOWN_OUTCOME",
    "RECONCILED",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _casefold(path: Path) -> str:
    text = str(path)
    return text.casefold() if WINDOWS else text


def is_drive_or_share_root(path: Path) -> bool:
    resolved = path.resolve()
    if resolved.parent == resolved:
        return True
    text = str(resolved)
    if text.startswith("\\\\") or text.startswith("//"):
        parts = text.replace("/", "\\").strip("\\").split("\\")
        return len(parts) <= 2
    return WINDOWS and len(text) <= 3 and text[1:2] == ":"


def is_unc(path: Path | str) -> bool:
    text = str(path).replace("/", "\\")
    return text.startswith("\\\\") or text.startswith("//")


def has_traversal(raw: str) -> bool:
    parts = raw.replace("\\", "/").split("/")
    return any(part == ".." for part in parts)


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if path.is_symlink():
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _is_protected(path: Path) -> bool:
    folded = _casefold(path.resolve())
    prefixes = PROTECTED_WINDOWS_PREFIXES if WINDOWS else PROTECTED_POSIX_PREFIXES
    return any(folded == prefix or folded.startswith(prefix + os.sep) for prefix in prefixes)


class RestoreTargetPolicy:
    """Allowlist-only restore targets with Windows-safe resolution."""

    def __init__(
        self,
        allowlist_roots: list[Path],
        *,
        workspace_roots: list[Path] | None = None,
    ) -> None:
        if not allowlist_roots:
            raise ValueError("restore allowlist must contain at least one isolated root")
        self.allowlist_roots = [root.resolve() for root in allowlist_roots]
        for root in self.allowlist_roots:
            if is_drive_or_share_root(root) or is_unc(root) or _is_protected(root):
                raise ValueError(f"allowlist root is not an isolated restore target: {root}")
        self.workspace_roots = [root.resolve() for root in (workspace_roots or [])]

    def resolve(self, target: str | Path) -> Path:
        raw = str(target).strip()
        if not raw:
            raise ValueError("restore target must be a non-empty absolute path")
        if is_unc(raw):
            raise ValueError("restore target must not be a UNC or share root")
        if has_traversal(raw):
            raise ValueError("restore target must not contain path traversal")
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise ValueError("restore target must be an absolute isolated path")
        resolved = candidate.resolve()
        if is_drive_or_share_root(resolved):
            raise ValueError("restore target must not be a drive or share root")
        if _is_protected(resolved):
            raise ValueError("restore target must not be a protected or system path")
        for workspace in self.workspace_roots:
            if _casefold(resolved) == _casefold(workspace):
                raise ValueError("restore target must not be a repository or workspace root")
            if _casefold(resolved).startswith(_casefold(workspace) + os.sep):
                raise ValueError("restore target must not resolve inside the workspace")
        if not any(
            _casefold(resolved) == _casefold(root)
            or _casefold(resolved).startswith(_casefold(root) + os.sep)
            for root in self.allowlist_roots
        ):
            raise ValueError("restore target is outside the configured isolation allowlist")
        self._reject_reparse_escape(candidate, resolved)
        return resolved

    def _reject_reparse_escape(self, candidate: Path, resolved: Path) -> None:
        current = candidate
        seen: set[str] = set()
        while True:
            key = _casefold(current)
            if key in seen:
                break
            seen.add(key)
            if _is_reparse(current):
                real = current.resolve()
                if not any(
                    _casefold(real) == _casefold(root)
                    or _casefold(real).startswith(_casefold(root) + os.sep)
                    for root in self.allowlist_roots
                ):
                    raise ValueError("restore target escapes isolation through a reparse point")
            if current.parent == current:
                break
            current = current.parent
        if _casefold(resolved) != _casefold(candidate.resolve()):
            raise ValueError("restore target resolution is inconsistent")


def verify_restored_tree(target: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    expected = {str(entry["path"]): entry for entry in manifest["entries"]}
    actual: dict[str, Path] = {}
    if target.exists():
        for path in target.rglob("*"):
            if path.is_file():
                actual[path.relative_to(target).as_posix()] = path
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    corrupt: list[str] = []
    for rel, entry in expected.items():
        found = actual.get(rel)
        if found is None:
            continue
        digest = hashlib.sha256(found.read_bytes()).hexdigest()
        size = found.stat().st_size
        if digest != str(entry["sha256"]).lower() or size != int(entry["size_bytes"]):
            corrupt.append(rel)
    if missing or extra or corrupt:
        status = "VERIFY_FAILED"
        detail = "missing" if missing else "extra" if extra else "corrupt"
    else:
        status = "VERIFY_PASSED"
        detail = "matched"
    return {
        "state": status,
        "detail": detail,
        "missing": missing,
        "extra": extra,
        "corrupt": corrupt,
        "backup_state_is_not_restore_state": True,
        "restore_state_is_not_verify_state": True,
    }


class RestoreIntentStore:
    """Durable restore intents with idempotent replay and explicit apply approval."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS restore_intents (
                    intent_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    target TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS restore_intent_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        self._db.close()

    def record_intent(
        self,
        *,
        idempotency_key: str,
        domain: str,
        target: Path,
        manifest_sha256: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        observed = now or _now()
        payload = {
            "idempotency_key": idempotency_key,
            "domain": domain,
            "target": str(target),
            "manifest_sha256": manifest_sha256,
        }
        encoded = json.dumps(payload, sort_keys=True)
        intent_id = f"RST-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"
        with self._db:
            existing = self._db.execute(
                "SELECT * FROM restore_intents WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) == encoded:
                    return dict(existing) | {"replayed": True}
                raise ValueError("conflicting restore intent under the same idempotency key")
            self._db.execute(
                """
                INSERT INTO restore_intents (
                    intent_id, idempotency_key, domain, target, manifest_sha256,
                    payload_json, state, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, 'INTENT_RECORDED', ?, ?)
                """,
                (
                    intent_id,
                    idempotency_key,
                    domain,
                    str(target),
                    manifest_sha256,
                    encoded,
                    observed.isoformat(),
                    observed.isoformat(),
                ),
            )
            self._audit(intent_id, "RECORD", "INTENT_RECORDED", observed)
        return {
            "intent_id": intent_id,
            "state": "INTENT_RECORDED",
            "replayed": False,
            "target": str(target),
        }

    def dry_run(
        self, intent_id: str, policy: RestoreTargetPolicy, *, now: datetime | None = None
    ) -> dict[str, Any]:
        row = self._require(intent_id)
        policy.resolve(str(row["target"]))
        self._transition(intent_id, "DRY_RUN_COMPLETE", now or _now(), action="DRY_RUN")
        return {"intent_id": intent_id, "state": "DRY_RUN_COMPLETE", "destructive": False}

    def apply(
        self,
        intent_id: str,
        *,
        source: Path,
        policy: RestoreTargetPolicy,
        approve: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not approve:
            raise ValueError("destructive restore apply requires explicit approval")
        row = self._require(intent_id)
        target = policy.resolve(str(row["target"]))
        if not source.is_dir():
            self._transition(intent_id, "FAILED", now or _now(), action="APPLY_FAILED")
            raise ValueError("restore source is missing")
        try:
            _copy_tree(source, target)
        except OSError:
            self._transition(intent_id, "UNKNOWN_OUTCOME", now or _now(), action="APPLY_UNKNOWN")
            raise
        self._transition(intent_id, "APPLIED", now or _now(), action="APPLY")
        return {"intent_id": intent_id, "state": "APPLIED", "target": str(target)}

    def verify(
        self,
        intent_id: str,
        manifest: dict[str, Any],
        policy: RestoreTargetPolicy,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._require(intent_id)
        target = policy.resolve(str(row["target"]))
        result = verify_restored_tree(target, manifest)
        state = "VERIFIED" if result["state"] == "VERIFY_PASSED" else "FAILED"
        self._transition(intent_id, state, now or _now(), action="VERIFY")
        return {"intent_id": intent_id, **result, "restore_state": state}

    def reconcile(self, intent_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        row = self._require(intent_id)
        target = Path(str(row["target"]))
        if str(row["state"]) != "UNKNOWN_OUTCOME":
            return dict(row) | {"reconciled": False}
        state = "RECONCILED" if target.exists() else "FAILED"
        self._transition(intent_id, state, now or _now(), action="RECONCILE")
        return {"intent_id": intent_id, "state": state, "reconciled": True}

    def get(self, intent_id: str) -> dict[str, Any]:
        return dict(self._require(intent_id))

    def _require(self, intent_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM restore_intents WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown restore intent: {intent_id}")
        return cast(sqlite3.Row, row)

    def _transition(self, intent_id: str, state: str, now: datetime, *, action: str) -> None:
        if state not in RESTORE_STATES:
            raise ValueError(f"invalid restore state: {state}")
        with self._db:
            self._db.execute(
                "UPDATE restore_intents SET state = ?, updated_at_utc = ? WHERE intent_id = ?",
                (state, now.isoformat(), intent_id),
            )
            self._audit(intent_id, action, state, now)

    def _audit(self, intent_id: str, action: str, state: str, now: datetime) -> None:
        self._db.execute(
            """
            INSERT INTO restore_intent_audit (intent_id, action, state, created_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            (intent_id, action, state, now.isoformat()),
        )


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())


def default_workspace_roots(project_root: Path) -> list[Path]:
    roots = [project_root.resolve()]
    if sys.platform == "win32":
        sibling = project_root.resolve().parent / "Project_X_worktrees"
        if sibling.exists():
            roots.append(sibling)
    return roots
