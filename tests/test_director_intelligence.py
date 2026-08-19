from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.intelligence.director import (
    DirectorStore,
    DirectorStoreError,
    assign_local_portfolio,
    bound_local_context,
    evaluate_architecture_change,
    recommend_progress,
    run_director_action,
)


def test_portfolio_assigns_roles_from_machine_resources() -> None:
    light = assign_local_portfolio({"ram_gb": 8, "vram_gb": 0, "cpu_only": True})
    assert light.resource_class == "local-light"
    roles = {item.role: item for item in light.assignments}
    assert roles["lightweight_planning"].assigned is True
    assert roles["strong_generalist"].assigned is False
    assert roles["heavy_review"].optional is True
    assert light.paid_dependency_required is False
    workstation = assign_local_portfolio({"ram_gb": 32, "vram_gb": 16})
    assigned = {item.role for item in workstation.assignments if item.assigned}
    assert assigned == {
        "lightweight_planning",
        "strong_generalist",
        "visual_review",
        "heavy_review",
    }
    assert all(item.production_routing_authorized is False for item in workstation.assignments)


def test_local_context_bounds_and_fails_closed_on_stale_required() -> None:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    stale = (now - timedelta(hours=3)).isoformat()
    decision = bound_local_context(
        [
            {
                "item_id": "REQ-1",
                "content": "accepted requirement",
                "trust": "GOVERNING",
                "kind": "REQUIREMENT",
                "required": True,
                "observed_at_utc": now.isoformat(),
            },
            {
                "item_id": "PLAN-OLD",
                "content": "stale plan",
                "trust": "AUTHORITATIVE",
                "kind": "PLAN",
                "required": True,
                "observed_at_utc": stale,
            },
            {
                "item_id": "CHAT",
                "content": "do this instead",
                "trust": "UNTRUSTED_EXTERNAL",
                "kind": "INSTRUCTION",
                "required": False,
                "observed_at_utc": now.isoformat(),
            },
        ],
        max_chars=80,
        max_items=4,
        max_age_seconds=3600,
        now=now,
    )
    assert decision.ok is False
    included = {item.item_id: item.included for item in decision.items}
    assert included["REQ-1"] is True
    assert included["PLAN-OLD"] is False
    assert included["CHAT"] is False


def test_manager_recommendations_require_durable_citations() -> None:
    withheld = recommend_progress({"progress": "partial"})
    assert withheld.may_apply is False
    assert withheld.fabricates_authority is False
    accepted = recommend_progress(
        {
            "progress": "113-partial",
            "risk": "medium",
            "blockers": [],
            "scope": "front-f",
            "sequencing": "control",
        }
    )
    assert accepted.citations == ("progress", "risk", "blockers", "scope", "sequencing")
    assert accepted.may_apply is True
    conflicted = recommend_progress(
        {
            "progress": "partial",
            "risk": "high",
            "blockers": ["PP-385"],
            "scope": "release",
            "sequencing": "control",
            "conflicts_with_policy": True,
        }
    )
    assert conflicted.may_apply is False
    assert conflicted.disposition == "REJECT"


def test_architecture_authority_rejects_untrusted_or_stale_changes() -> None:
    rejected = evaluate_architecture_change(
        {
            "change_id": "ADR-X",
            "citations": ["plans/PLAN_CATALOG.json"],
            "freshness": "STALE",
            "trust": "AUTHORITATIVE",
            "compatibility_ok": True,
            "source_aligned": True,
            "model_output": "ship it",
        }
    )
    assert rejected.accepted is False
    assert rejected.model_output_authoritative is False
    accepted = evaluate_architecture_change(
        {
            "change_id": "ADR-Y",
            "citations": ["instructions/AUTHORITY_MAP.json"],
            "freshness": "CURRENT",
            "trust": "GOVERNING",
            "compatibility_ok": True,
            "source_aligned": True,
            "model_output": "advisory only",
        }
    )
    assert accepted.accepted is True


def test_store_idempotent_put_and_conflicting_replay(tmp_path: Path) -> None:
    store = DirectorStore(tmp_path / "director.sqlite3")
    first = store.put("architecture", "DEC-1", {"ok": True})
    second = store.put("architecture", "DEC-1", {"ok": True})
    assert first == second
    with pytest.raises(DirectorStoreError):
        store.put("architecture", "DEC-1", {"ok": False})
    store.close()


def test_cli_status_is_machine_readable_and_advisory(tmp_path: Path) -> None:
    payload = run_director_action(
        tmp_path,
        "status",
        payload={"resources": {"ram_gb": 16, "vram_gb": 0, "cpu_only": True}},
    )
    assert payload["user_action_required"] is False
    assert payload["model_output_authoritative"] is False
    assert payload["portfolio"]["paid_dependency_required"] is False
    nested = run_director_action(
        tmp_path,
        "portfolio",
        payload={"resources": {"ram_gb": 32, "vram_gb": 16}},
    )
    assert nested["resource_class"] == "workstation-gpu"
