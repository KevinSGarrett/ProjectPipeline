from pathlib import Path

from project_pipeline.validation.autonomy_language import (
    validate_autonomous_external_preconditions,
)


def test_repository_active_truth_has_no_retired_human_work_state() -> None:
    root = Path(__file__).resolve().parents[1]
    assert validate_autonomous_external_preconditions(root) == []


def test_gate_rejects_retired_state_in_active_runtime(tmp_path: Path) -> None:
    source = tmp_path / "src" / "project_pipeline" / "runtime.py"
    source.parent.mkdir(parents=True)
    source.write_text('STATE = "HUMAN' + '_REQUIRED"\n', encoding="utf-8")
    errors = validate_autonomous_external_preconditions(tmp_path)
    assert len(errors) == 1
    assert "runtime.py" in errors[0]


def test_gate_rejects_retired_incident_and_approval_apis(tmp_path: Path) -> None:
    source = tmp_path / "src" / "project_pipeline" / "runtime.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "class Human" + "RequiredIncident:\n    requires_" + "human_approval = True\n",
        encoding="utf-8",
    )
    errors = validate_autonomous_external_preconditions(tmp_path)
    assert len(errors) == 1
    assert "runtime.py" in errors[0]
