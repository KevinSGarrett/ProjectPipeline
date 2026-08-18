"""Shared PP-379 recovery fixtures that do not depend on a local worktree path."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE_DURABLE = Path(__file__).resolve().parent / "fixtures" / "pp379_durable"
PUBLIC_ATTESTATION_REF = "evidence/pp379_writer_attestation_evidence.json"
PUBLIC_QUALIFICATION_REF = "evidence/pp379_writer_provider_qualification_evidence.json"
HISTORICAL_RECEIPT_REF = "evidence/control_completion_post_remediation.json"


def source_root() -> Path:
    return REPO


def durable_dir() -> Path:
    return FIXTURE_DURABLE


def historical_receipt() -> Path:
    return REPO / HISTORICAL_RECEIPT_REF


def copy_agent_registry(dest_root: Path) -> None:
    dest = dest_root / "config" / "agents"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / "config" / "agents", dest, dirs_exist_ok=True)


def copy_takeover_config(dest_root: Path) -> None:
    dest = dest_root / "config"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "config" / "cursor_takeover.json", dest / "cursor_takeover.json")


def copy_historical_receipt(dest_root: Path) -> None:
    dest = dest_root / "evidence"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(historical_receipt(), dest / Path(HISTORICAL_RECEIPT_REF).name)


def isolated_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    copy_agent_registry(repo)
    copy_takeover_config(repo)
    copy_historical_receipt(repo)
    return repo


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
