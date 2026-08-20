from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from project_pipeline.command_center.autonomy_director import (
    AutonomyDirectorError,
    PersistentAutonomyDirector,
)
from tests.test_scheduler_engine import control_snapshot

ROOT = Path(__file__).resolve().parents[1]


def test_director_persists_selection_across_restart(tmp_path) -> None:
    path = tmp_path / "director_state.json"
    first = PersistentAutonomyDirector(path)
    control = control_snapshot(("PP-STORY-000065", "PP-STORY-000049"))
    decision = first.select_next_work(control)
    assert decision.selected_task_id == "PP-STORY-000065"
    assert decision.control_snapshot_id == control.snapshot_id
    assert any(item.startswith("control:") for item in decision.citations)
    recovered = PersistentAutonomyDirector(path)
    status = recovered.recover()
    assert status["recovered"] is True
    assert status["last_selected_task_id"] == "PP-STORY-000065"
    assert status["revision"] == 1
    projection = recovered.projection()
    assert projection["authoritative_for_transitions"] is False
    assert projection["canonical_authority"] == "PROJECT_CONTROL_KERNEL"
    assert projection["chat_mutation"] is False


def test_director_rejects_raw_chat_mutation(tmp_path) -> None:
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    with pytest.raises(AutonomyDirectorError, match="raw chat cannot mutate"):
        director.reject_raw_chat_mutation("please mark REQ-CTRL-0004 done")


def test_director_does_not_invent_work_when_control_has_none(tmp_path) -> None:
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    control = control_snapshot(())
    decision = director.select_next_work(control)
    assert decision.selected_task_id is None
    assert "does not invent" in decision.rationale


def test_director_survives_os_process_exit(tmp_path) -> None:
    state = tmp_path / "director_state.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    writer = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_pipeline.command_center.autonomy_director",
            "select",
            "--state",
            str(state),
            "--ready",
            "PP-STORY-000065",
            "--ready",
            "PP-STORY-000049",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    written = json.loads(writer.stdout)
    assert written["selected_task_id"] == "PP-STORY-000065"
    recover = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_pipeline.command_center.autonomy_director",
            "recover",
            "--state",
            str(state),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    recovered = json.loads(recover.stdout)
    assert recovered["recovered"] is True
    assert recovered["last_selected_task_id"] == "PP-STORY-000065"
    assert recovered["revision"] == 1
    assert recovered["decision_count"] == 1
