"""Validate compact cycle handoffs against existing project-state artifacts.

This is not a second source of truth. It rejects contradictory or voluntary-stop
handoffs by checking the markdown plus the existing delivery meter, fresh-delivery
proof, and a compact packet derived from Git/Jira/qualification ledgers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json

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
