"""Validate compact cycle handoffs against existing project-state artifacts.

This is not a second source of truth. It rejects contradictory or voluntary-stop
handoffs by checking the markdown plus the existing delivery meter, fresh-delivery
proof, and a compact packet derived from Git/Jira/qualification ledgers.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from project_pipeline.assurance.cycle_workload import (
    derive_requirement_movements,
    validate_requirement_movement_ledger,
)
from project_pipeline.io import read_json
from project_pipeline.jira_steward.identity import parse_utc

REQUIRED_SECTIONS = (
    "exact integrated main",
    "open pr",
    "accepted commits",
    "jira local/live",
    "pp-384 live",
    "pp-385",
    "completion gate",
    "external precondition",
    "superseded",
    "next autonomous action",
)

FORBIDDEN_HANDOFF_PHRASES = (
    "next human",
    "human-owned work",
    "await human",
    "awaiting human",
    "requires operator session",
    "operator must",
    "ask the operator",
    "have the operator",
    "supply the token",
    "please run",
    "manual review required",
    "HUMAN" + "_REQUIRED",
)

NOTHING_LEFT_PHRASES = (
    "nothing else to implement",
    "nothing remained implementable",
    "no remaining implementable work",
)

OPERATOR_COMMAND_RE = re.compile(
    r"(?i)\b(operator|human|user)\b.{0,80}\b(run|execute|please)\b.{0,40}"
    r"(`[^`]+`|python\s+-m|pytest\b|git\s+)"
)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def validate_cycle_handoff(
    *,
    handoff_text: str,
    meter: dict[str, Any],
    proof: dict[str, Any],
    packet: dict[str, Any],
    floor_script_exit_code: int | None = None,
    floor_script_ran: bool = False,
) -> dict[str, Any]:
    findings: list[str] = []
    if any(ord(char) < 32 and char not in "\n\r\t" for char in handoff_text):
        findings.append("handoff contains ASCII control characters")
    normalized = _normalize(handoff_text)
    combined = _normalize(handoff_text + "\n" + _as_text(meter) + "\n" + _as_text(packet))

    for section in REQUIRED_SECTIONS:
        if section not in normalized:
            findings.append(f"missing required section: {section}")

    for phrase in FORBIDDEN_HANDOFF_PHRASES:
        if phrase.lower() in combined:
            findings.append(f"forbidden human-work phrase: {phrase}")

    if OPERATOR_COMMAND_RE.search(handoff_text):
        findings.append("handoff presents an exact command as work for a person")

    origin_heads = [str(item) for item in packet.get("origin_main_heads", [])]
    supersessions = packet.get("superseded_claims") or meter.get("superseded_claims") or []
    if len(set(origin_heads)) > 1 and not supersessions:
        findings.append("multiple contradictory origin/main heads without supersession markers")

    for row in packet.get("pull_requests", []):
        if bool(row.get("open")) and bool(row.get("merged")):
            findings.append(f"PR labeled both open and merged: {row.get('number')}")

    for row in packet.get("worktrees", []):
        labeled_active = str(row.get("status", "")).lower() == "active"
        missing_path = not Path(str(row.get("path", ""))).exists()
        if labeled_active and missing_path:
            findings.append(f"deleted worktree labeled active: {row.get('path')}")

    recoverable = bool(packet.get("recoverable_evidence_present")) or bool(
        packet.get("stale_dependency_projection")
    )
    if recoverable and any(phrase in combined for phrase in NOTHING_LEFT_PHRASES):
        findings.append(
            "nothing else to implement claimed while recoverable evidence or stale "
            "dependency projection exists"
        )

    if not meter:
        findings.append("missing delivery meter")
    if not proof:
        findings.append("missing fresh-delivery proof")

    claims_floor_pass = (
        bool(packet.get("claims_floor_pass"))
        or "cycle_011_massive_autonomous_delivery_pass" in combined
    )
    if claims_floor_pass and not (floor_script_ran and floor_script_exit_code == 0):
        findings.append("floor-pass claim without successful Assert-CycleFloor.ps1 execution")

    return {
        "valid": not findings,
        "findings": findings,
        "section_count": len(REQUIRED_SECTIONS),
    }


def load_and_validate_cycle_handoff(
    *,
    handoff_path: Path,
    meter_path: Path,
    proof_path: Path,
    packet_path: Path,
    floor_script_exit_code: int | None = None,
    floor_script_ran: bool = False,
) -> dict[str, Any]:
    missing = [
        str(path)
        for path in (handoff_path, meter_path, proof_path, packet_path)
        if not path.is_file()
    ]
    if missing:
        return {
            "valid": False,
            "findings": [f"missing required artifact: {path}" for path in missing],
            "section_count": len(REQUIRED_SECTIONS),
        }
    return validate_cycle_handoff(
        handoff_text=handoff_path.read_text(encoding="utf-8"),
        meter=read_json(meter_path),
        proof=read_json(proof_path),
        packet=read_json(packet_path),
        floor_script_exit_code=floor_script_exit_code,
        floor_script_ran=floor_script_ran,
    )


REQUIRED_PACKET_FILES = (
    "DELIVERY_METER.json",
    "FRESH_DELIVERY_PROOF.json",
    "git_identity_verification.json",
    "validation_matrix.json",
    "front_status.json",
    "requirement_movement_ledger.json",
    "jira_reconciliation_ledger.json",
    "external_write_receipts.json",
    "campaign_reconciliation.json",
    "cleanup_inventory.json",
    "handoffs/Combined-Agent.md",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write through a temporary file then replace so partial bytes cannot persist."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding=encoding, newline="\n")
    temporary.replace(path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def write_cycle_packet_atomically(
    directory: Path, artifacts: dict[str, str | dict[str, Any]]
) -> None:
    """Write every packet file, then the handoff sidecar last, from one observation."""

    for relative, payload in artifacts.items():
        target = directory / relative
        if isinstance(payload, str):
            atomic_write_text(target, payload)
        else:
            atomic_write_json(target, payload)
    handoff = directory / "handoffs" / "Combined-Agent.md"
    if handoff.is_file():
        digest = sha256_bytes(handoff.read_bytes())
        atomic_write_text(directory / "handoffs" / "Combined-Agent.md.sha256", f"{digest}\n")


def _artifact_head(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("main_sha", "origin_main", "sha", "head_sha", "integrated_main"):
        item = value.get(key)
        if isinstance(item, str) and item:
            return item
        if isinstance(item, dict):
            nested = item.get("sha") or item.get("head")
            if isinstance(nested, str) and nested:
                return nested
    return None


def validate_cycle_packet_integrity(
    *,
    directory: Path,
    observation: dict[str, Any],
) -> dict[str, Any]:
    """Hard-fail a cycle packet that is stale, partial, or internally contradictory."""

    findings: list[str] = []
    files = {name: directory / name for name in REQUIRED_PACKET_FILES}
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        return {
            "valid": False,
            "findings": [f"missing required packet file: {name}" for name in missing],
        }

    payloads: dict[str, Any] = {}
    for name, path in files.items():
        if name.endswith(".md"):
            payloads[name] = path.read_text(encoding="utf-8")
        else:
            payloads[name] = read_json(path)

    fetched_main = str(observation.get("origin_main") or "")
    fetched_tree = str(observation.get("origin_main_tree") or "")
    packet_main = str(
        observation.get("packet_main")
        or _artifact_head(payloads["git_identity_verification.json"])
        or _artifact_head(payloads["FRESH_DELIVERY_PROOF.json"])
        or ""
    )
    packet_tree = str(
        (payloads["git_identity_verification.json"] or {}).get("tree")
        or (payloads["git_identity_verification.json"] or {}).get("tree_sha")
        or ""
    )
    if fetched_main and packet_main and fetched_main != packet_main:
        findings.append("packet main/tree differs from freshly fetched remote main")
    if fetched_tree and packet_tree and fetched_tree != packet_tree:
        findings.append("packet main/tree differs from freshly fetched remote main")

    latest_write = parse_utc(str(observation.get("latest_write_at_utc") or ""))
    packet_time = parse_utc(
        str(
            (payloads["FRESH_DELIVERY_PROOF.json"] or {}).get("observed_at_utc")
            or (payloads["DELIVERY_METER.json"] or {}).get("observed_at_utc")
            or ""
        )
    )
    if latest_write and packet_time and packet_time < latest_write:
        findings.append("packet timestamp predates a later merge or Jira write")

    handoff_bytes = files["handoffs/Combined-Agent.md"].read_bytes()
    actual_digest = sha256_bytes(handoff_bytes)
    sidecar_path = directory / "handoffs" / "Combined-Agent.md.sha256"
    if not sidecar_path.is_file():
        findings.append("handoff sidecar is missing")
    else:
        recorded = sidecar_path.read_text(encoding="utf-8").strip().split()[0]
        if recorded != actual_digest:
            findings.append("sidecar differs from actual bytes")

    heads = {
        name: _artifact_head(payloads[name])
        for name in (
            "DELIVERY_METER.json",
            "FRESH_DELIVERY_PROOF.json",
            "git_identity_verification.json",
            "validation_matrix.json",
            "front_status.json",
            "requirement_movement_ledger.json",
            "external_write_receipts.json",
            "cleanup_inventory.json",
        )
    }
    named_heads = {name: value for name, value in heads.items() if value}
    if fetched_main:
        handoff_head = (
            fetched_main
            if fetched_main in str(payloads["handoffs/Combined-Agent.md"])
            else named_heads.get("git_identity_verification.json")
        )
        if handoff_head:
            named_heads["handoffs/Combined-Agent.md"] = handoff_head
    unique_heads = {value for value in named_heads.values() if value}
    if len(unique_heads) > 1:
        findings.append(
            "meter, proof, identity verification, validation matrix, movement ledger, "
            "receipts, cleanup inventory, and handoff name different heads"
        )

    movements = payloads["requirement_movement_ledger.json"]
    movement_rows = movements.get("rows") if isinstance(movements, dict) else movements
    if observation.get("requirement_movements") and not movement_rows:
        findings.append("required ledger is empty despite observed movements/writes")
    git_root = observation.get("git_root")
    base_sha = str(observation.get("base_sha") or "")
    if git_root and fetched_main and base_sha:
        expected_movements = derive_requirement_movements(
            Path(str(git_root)),
            base_ref=base_sha,
            head_ref=fetched_main,
        )
        if not isinstance(movements, dict):
            findings.append("requirement movement ledger is not an object")
        else:
            movement_findings = validate_requirement_movement_ledger(movements, expected_movements)
            findings.extend(item.message for item in movement_findings)
            ledger_base = str(movements.get("base_sha") or movements.get("base") or "")
            ledger_head = str(movements.get("head_sha") or movements.get("head") or "")
            ledger_tree = str(movements.get("head_tree") or movements.get("tree") or "")
            if ledger_base and ledger_base != base_sha:
                findings.append("stale-head or wrong-base requirement ledger")
            if ledger_head and ledger_head != fetched_main:
                findings.append("stale-head or wrong-head requirement ledger")
            if fetched_tree and ledger_tree and ledger_tree != fetched_tree:
                findings.append("contradictory-tree requirement ledger")
    receipts = payloads["external_write_receipts.json"]
    receipt_rows = receipts.get("receipts") if isinstance(receipts, dict) else receipts
    if observation.get("external_writes") and not receipt_rows:
        findings.append("required ledger is empty despite observed movements/writes")
    expected_prs = observation.get("required_pr_numbers")
    if expected_prs:
        observed_prs: set[int] = set()
        if isinstance(receipt_rows, list):
            for row in receipt_rows:
                if not isinstance(row, dict):
                    continue
                number = row.get("pr") or row.get("number") or row.get("pull_request")
                if number is not None:
                    observed_prs.add(int(number))
        missing_prs = sorted(int(item) for item in expected_prs if int(item) not in observed_prs)
        if missing_prs:
            findings.append(f"incomplete PR receipt range: missing {missing_prs}")
    sidecar_path = directory / "handoffs" / "Combined-Agent.md.sha256"
    payload_path = files["handoffs/Combined-Agent.md"]
    if (
        sidecar_path.is_file()
        and payload_path.is_file()
        and sidecar_path.stat().st_mtime_ns < payload_path.stat().st_mtime_ns
    ):
        findings.append("sidecar-written-before-payload")

    github_raw = observation.get("github")
    github: dict[str, Any] = github_raw if isinstance(github_raw, dict) else {}
    listed_open = github.get("open_pull_numbers")
    packet_open = (payloads["front_status.json"] or {}).get("open_prs")
    if listed_open is not None and packet_open is not None and listed_open != packet_open:
        findings.append("a listed PR/open lane contradicts GitHub")
    if github.get("remote_heads") and github.get("remote_heads") != observation.get(
        "observed_remote_heads", github.get("remote_heads")
    ):
        findings.append("a listed PR/open lane contradicts GitHub")

    live_raw = observation.get("live")
    live: dict[str, Any] = live_raw if isinstance(live_raw, dict) else {}
    for key in ("jira", "campaign", "worktrees"):
        packet_fact: Any = live.get(f"packet_{key}")
        observed_fact: Any = live.get(f"observed_{key}")
        if packet_fact is not None and observed_fact is not None and packet_fact != observed_fact:
            findings.append("a live Jira/campaign/worktree fact contradicts readback")

    compact_raw = observation.get("compact_packet")
    compact_packet: dict[str, Any] = (
        compact_raw
        if isinstance(compact_raw, dict)
        else {
            "origin_main_heads": [fetched_main] if fetched_main else [],
            "pull_requests": [],
            "worktrees": [],
            "recoverable_evidence_present": False,
            "stale_dependency_projection": False,
            "claims_floor_pass": False,
            "superseded_claims": ["cycle-14-accounting-correction"],
        }
    )
    compact = validate_cycle_handoff(
        handoff_text=str(payloads["handoffs/Combined-Agent.md"]),
        meter=payloads["DELIVERY_METER.json"]
        if isinstance(payloads["DELIVERY_METER.json"], dict)
        else {},
        proof=payloads["FRESH_DELIVERY_PROOF.json"]
        if isinstance(payloads["FRESH_DELIVERY_PROOF.json"], dict)
        else {},
        packet=compact_packet,
    )
    if not compact["valid"]:
        findings.extend(str(item) for item in compact["findings"])

    return {"valid": not findings, "findings": findings, "handoff_sha256": actual_digest}
