from __future__ import annotations

from pathlib import Path

from project_pipeline.autonomy_runtime.golden import (
    BEHAVIOR_KEYS,
    GoldenJourneyHarness,
    validate_evidence_map,
)


def test_local_real_golden_journey(tmp_path: Path) -> None:
    harness = GoldenJourneyHarness(tmp_path / "journey")
    evidence = harness.run()
    validate_evidence_map(evidence)
    assert evidence["pp383_acceptance"] is True
    assert evidence["2_select_missing_task"]["task_id"] == "PP-GOLDEN-001"
    assert evidence["5_change_production_source"]["changed"] is True
    assert evidence["6_change_fixture_tests"]["changed"] is True
    assert len(evidence["8_worker_commit"]["sha"]) == 40
    assert (
        evidence["11_integrated_main_sha"]["integrated_ref"]
        == evidence["11_integrated_main_sha"]["main_readback"]
    )
    assert evidence["12_jira_reconciliation"]["state"] == "RECONCILED"
    assert evidence["13_restart_continuation"]["same_operation_id"] is True
    assert evidence["14_worker_loss_recovery"]["stale_rejected"] is True
    assert evidence["15_human_required_and_unaffected"]["human_required"] == "HUMAN_REQUIRED"
    assert evidence["15_human_required_and_unaffected"]["unaffected_completed"] is True
    assert evidence["15_human_required_and_unaffected"]["command_center_incident_ids"]
    assert evidence["16_next_eligible_selection"]["next_eligible_task_id"] == "PP-GOLDEN-002"
    assert all(key in evidence for key in BEHAVIOR_KEYS)
    assert str(harness.evidence_path).startswith(str(tmp_path))
