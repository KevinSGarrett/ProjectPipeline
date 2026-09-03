"""Admitted qualified-draft inventory for exact-byte publication.

Publication may reuse a cache only when every admitted byte still matches.
A rebuild is not a license to replace the qualified draft or its assets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_pipeline.github_steward.asset_names import canonical_release_asset_name
from project_pipeline.github_steward.errors import GitHubStewardError

ADMITTED_INVENTORY_NAME = "admitted_release_inventory.json"


def admitted_inventory_path(evidence_path: Path) -> Path:
    return evidence_path.resolve() / ADMITTED_INVENTORY_NAME


def write_admitted_release_inventory(evidence_path: Path, inventory: dict[str, Any]) -> Path:
    path = admitted_inventory_path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = validate_admitted_release_inventory(inventory)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != normalized:
            raise GitHubStewardError("admitted release inventory is immutable")
        return path
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_admitted_release_inventory(evidence_path: Path) -> dict[str, Any]:
    path = admitted_inventory_path(evidence_path)
    if not path.is_file():
        raise GitHubStewardError("publication requires an admitted release inventory")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubStewardError("admitted release inventory is malformed") from exc
    return validate_admitted_release_inventory(payload)


def validate_admitted_release_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GitHubStewardError("admitted release inventory is malformed")
    try:
        draft_id = int(payload["draft_id"])
        tag_name = str(payload["tag_name"])
        target = str(payload["target_commitish"]).lower()
        source_sha = str(payload["source_sha"]).lower()
        source_tree = str(payload["source_tree"]).lower()
        assets = payload["assets"]
    except (KeyError, TypeError, ValueError) as exc:
        raise GitHubStewardError("admitted release inventory is incomplete") from exc
    if draft_id < 1:
        raise GitHubStewardError("admitted draft identity is invalid")
    if len(source_sha) != 40 or len(source_tree) != 40:
        raise GitHubStewardError("admitted inventory is not bound to a source SHA/tree")
    if source_sha != target:
        raise GitHubStewardError("admitted draft target differs from the source SHA")
    if not isinstance(assets, list) or not assets:
        raise GitHubStewardError("admitted inventory requires bound release assets")
    normalized_assets: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in assets:
        if not isinstance(item, dict):
            raise GitHubStewardError("admitted asset record is malformed")
        name = canonical_release_asset_name(str(item.get("name") or ""))
        digest = str(item.get("sha256") or "").lower()
        try:
            size_bytes = int(item["size_bytes"])
            asset_id = int(item["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubStewardError("admitted asset identity is incomplete") from exc
        if not name or len(digest) != 64 or size_bytes < 1 or asset_id < 1:
            raise GitHubStewardError("admitted asset identity is invalid")
        if name in names:
            raise GitHubStewardError("admitted assets collide after filename normalization")
        names.add(name)
        normalized_assets.append(
            {
                "id": asset_id,
                "name": name,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
    normalized_assets.sort(key=lambda item: item["name"])
    return {
        "draft_id": draft_id,
        "tag_name": tag_name,
        "target_commitish": target,
        "source_sha": source_sha,
        "source_tree": source_tree,
        "assets": normalized_assets,
    }


def admitted_asset_sha256s(inventory: dict[str, Any]) -> dict[str, str]:
    return {str(item["name"]): str(item["sha256"]) for item in inventory["assets"]}
