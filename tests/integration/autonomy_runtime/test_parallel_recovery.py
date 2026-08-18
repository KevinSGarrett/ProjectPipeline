from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from multiprocessing import Process, Queue
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.lanes import (
    LaneRegistry,
    canonicalize_resource,
    canonicalize_resources,
)
from project_pipeline.autonomy_runtime.recovery import DurableRecoveryService, recover_lane_loss


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def _claim_worker(db_path: str, lane_id: str, resource: str, output: Queue) -> None:
    registry = LaneRegistry(Path(db_path))
    lease = registry.claim(
        lane_id=lane_id,
        worker_id=f"worker-{lane_id}",
        resources=(resource,),
        lease_seconds=5,
    )
    output.put((lane_id, lease.fencing_token if lease else None))
    registry.close()


def _record_worker(
    db_path: str,
    lane_id: str,
    worker_id: str,
    token: str,
    fingerprint: str,
    output: Queue,
) -> None:
    registry = LaneRegistry(Path(db_path))
    accepted = registry.record_result(
        lane_id=lane_id,
        worker_id=worker_id,
        fencing_token=token,
        result_fingerprint=fingerprint,
    )
    output.put((worker_id, accepted, fingerprint))
    registry.close()


def test_overlapping_exclusive_claims_never_execute_concurrently(tmp_path: Path) -> None:
    db_path = tmp_path / "lanes.sqlite3"
    output: Queue = Queue()
    first = Process(target=_claim_worker, args=(str(db_path), "lane-a", "PATH:shared", output))
    second = Process(target=_claim_worker, args=(str(db_path), "lane-b", "PATH:shared", output))
    first.start()
    second.start()
    first.join()
    second.join()
    results = [output.get_nowait(), output.get_nowait()]
    acquired = [item for item in results if item[1] is not None]
    denied = [item for item in results if item[1] is None]
    assert len(acquired) == 1
    assert len(denied) == 1


def test_claim_requires_non_empty_normalized_resources(tmp_path: Path) -> None:
    registry = LaneRegistry(tmp_path / "lanes.sqlite3")
    with pytest.raises(ValueError):
        registry.claim(
            lane_id="lane-empty",
            worker_id="worker-empty",
            resources=("", "   "),
            lease_seconds=5,
        )
    with pytest.raises(ValueError, match="duplicate"):
        canonicalize_resources(("PATH:shared", "PATH:shared"))
    left = canonicalize_resource(r"PATH:C:\Project_X\Lane")
    right = canonicalize_resource(r"PATH:c:\project_x\lane")
    assert left == right
    registry.close()


def test_unaffected_lane_continues_and_stale_fencing_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "lanes.sqlite3"
    registry = LaneRegistry(db_path)
    lane_a = registry.claim(
        lane_id="lane-a",
        worker_id="worker-a",
        resources=("PATH:exclusive-a",),
        lease_seconds=5,
    )
    lane_b = registry.claim(
        lane_id="lane-b",
        worker_id="worker-b",
        resources=("PATH:exclusive-b",),
        lease_seconds=5,
    )
    assert lane_a is not None
    assert lane_b is not None
    assert registry.record_result(
        lane_id="lane-b",
        worker_id="worker-b",
        fencing_token=lane_b.fencing_token,
        result_fingerprint="ok-lane-b",
    )
    assert not registry.record_result(
        lane_id="lane-a",
        worker_id="worker-a",
        fencing_token="stale-token",
        result_fingerprint="should-fail",
    )
    registry.close()


def test_clock_injection_expires_lease_without_sleep(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = LaneRegistry(tmp_path / "lanes.sqlite3", clock=clock)
    lease = registry.claim(
        lane_id="lane-clock",
        worker_id="worker-clock",
        resources=("PATH:clock",),
        lease_seconds=10,
    )
    assert lease is not None
    clock.advance(11)
    assert not registry.renew(
        lane_id="lane-clock",
        worker_id="worker-clock",
        fencing_token=lease.fencing_token,
        lease_seconds=10,
    )
    replacement = registry.claim(
        lane_id="lane-clock",
        worker_id="worker-clock-2",
        resources=("PATH:clock",),
        lease_seconds=10,
    )
    assert replacement is not None
    assert replacement.attempt_number == 2
    assert replacement.fencing_token != lease.fencing_token
    registry.close()


def test_real_process_loss_recovers_same_logical_lane(tmp_path: Path) -> None:
    db_path = tmp_path / "lanes.sqlite3"
    token_path = tmp_path / "lost.token"
    script = tmp_path / "lossy_worker.py"
    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "from project_pipeline.autonomy_runtime.lanes import LaneRegistry",
                f"registry = LaneRegistry(Path(r'{db_path}'))",
                "lease = registry.claim(",
                "    lane_id='lane-a',",
                "    worker_id='worker-lost',",
                "    resources=('PATH:exclusive-a',),",
                "    lease_seconds=120,",
                ")",
                "assert lease is not None",
                "assert registry.heartbeat(",
                "    lane_id='lane-a',",
                "    worker_id='worker-lost',",
                "    fencing_token=lease.fencing_token,",
                "    intent={'phase': 'dispatch'},",
                ")",
                f"Path(r'{token_path}').write_text(lease.fencing_token + '\\n' + lease.attempt_id, encoding='utf-8')",
                "registry.close()",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        cwd=str(Path(__file__).resolve().parents[3]),
    )
    assert completed.returncode == 0
    stale_token, stale_attempt = token_path.read_text(encoding="utf-8").strip().split("\n")
    registry = LaneRegistry(db_path)
    incident = recover_lane_loss(
        registry=registry,
        lane_id="lane-a",
        stale_fencing_token=stale_token,
        stale_worker_id="worker-lost",
    )
    assert incident.state == "RECOVERED"
    assert incident.reason == "WORKER_LOSS"
    assert incident.attempt_id == stale_attempt
    assert not registry.renew(
        lane_id="lane-a",
        worker_id="worker-lost",
        fencing_token=stale_token,
    )
    assert not registry.release(
        lane_id="lane-a",
        worker_id="worker-lost",
        fencing_token=stale_token,
    )
    assert not registry.record_result(
        lane_id="lane-a",
        worker_id="worker-lost",
        fencing_token=stale_token,
        result_fingerprint="stale-result",
    )
    replacement = registry.claim(
        lane_id="lane-a",
        worker_id="worker-replacement",
        resources=("PATH:exclusive-a",),
        lease_seconds=30,
    )
    assert replacement is not None
    assert replacement.attempt_number == 2
    assert replacement.attempt_id != stale_attempt
    assert registry.record_result(
        lane_id="lane-a",
        worker_id="worker-replacement",
        fencing_token=replacement.fencing_token,
        result_fingerprint="replacement-result",
    )
    assert registry.result_for_attempt(stale_attempt) is None
    assert registry.result_for_attempt(replacement.attempt_id)["result_fingerprint"] == (
        "replacement-result"
    )
    assert registry.heartbeats_for_attempt(stale_attempt)
    registry.close()


def test_stale_and_replacement_result_race_has_one_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "lanes.sqlite3"
    registry = LaneRegistry(db_path)
    original = registry.claim(
        lane_id="lane-race",
        worker_id="worker-stale",
        resources=("PATH:race",),
        lease_seconds=60,
    )
    assert original is not None
    recover_lane_loss(
        registry=registry,
        lane_id="lane-race",
        stale_fencing_token=original.fencing_token,
        stale_worker_id="worker-stale",
    )
    replacement = registry.claim(
        lane_id="lane-race",
        worker_id="worker-new",
        resources=("PATH:race",),
        lease_seconds=60,
    )
    assert replacement is not None
    registry.close()

    output: Queue = Queue()
    stale = Process(
        target=_record_worker,
        args=(
            str(db_path),
            "lane-race",
            "worker-stale",
            original.fencing_token,
            "stale-result",
            output,
        ),
    )
    fresh = Process(
        target=_record_worker,
        args=(
            str(db_path),
            "lane-race",
            "worker-new",
            replacement.fencing_token,
            "replacement-result",
            output,
        ),
    )
    stale.start()
    fresh.start()
    stale.join()
    fresh.join()
    results = [output.get_nowait(), output.get_nowait()]
    winners = [item for item in results if item[1] is True]
    losers = [item for item in results if item[1] is False]
    assert len(winners) == 1
    assert winners[0][0] == "worker-new"
    assert winners[0][2] == "replacement-result"
    assert len(losers) == 1
    assert losers[0][0] == "worker-stale"
    restarted = LaneRegistry(db_path)
    assert restarted.result_for_attempt(replacement.attempt_id)["result_fingerprint"] == (
        "replacement-result"
    )
    assert restarted.result_for_attempt(original.attempt_id) is None
    restarted.close()


def test_unsolvable_lane_is_blocked_external_while_other_completes(tmp_path: Path) -> None:
    db_path = tmp_path / "lanes.sqlite3"
    registry = LaneRegistry(db_path)
    blocked = registry.claim(
        lane_id="lane-blocked",
        worker_id="worker-blocked",
        resources=("PATH:blocked",),
        lease_seconds=60,
    )
    healthy = registry.claim(
        lane_id="lane-healthy",
        worker_id="worker-healthy",
        resources=("PATH:healthy",),
        lease_seconds=60,
    )
    assert blocked is not None
    assert healthy is not None
    incident = recover_lane_loss(
        registry=registry,
        lane_id="lane-blocked",
        stale_fencing_token="not-the-live-token",
        stale_worker_id="unknown-owner",
    )
    assert incident.state == "BLOCKED_EXTERNAL"
    assert incident.reason == "UNSOLVABLE_LIVE_LEASE_WITHOUT_MATCHING_FENCE"
    assert registry.record_result(
        lane_id="lane-healthy",
        worker_id="worker-healthy",
        fencing_token=healthy.fencing_token,
        result_fingerprint="healthy-complete",
    )
    persisted = registry.list_incidents("lane-blocked")
    assert persisted[-1].disposition == "BLOCKED_EXTERNAL"
    assert persisted[-1].failure_fingerprint
    registry.close()

    restarted = DurableRecoveryService.open(db_path)
    incidents = restarted.incidents("lane-blocked")
    assert incidents[-1].state == "BLOCKED_EXTERNAL"
    assert restarted.registry.result_for_attempt(healthy.attempt_id)["result_fingerprint"] == (
        "healthy-complete"
    )
    restarted.close()


def test_retry_exhaustion_persists_autonomous_external_block(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = LaneRegistry(tmp_path / "lanes.sqlite3", clock=clock, max_attempts=2)
    first = registry.claim(
        lane_id="lane-retry",
        worker_id="w1",
        resources=("PATH:retry",),
        lease_seconds=10,
    )
    assert first is not None
    recover_lane_loss(
        registry=registry,
        lane_id="lane-retry",
        stale_fencing_token=first.fencing_token,
        stale_worker_id="w1",
    )
    second = registry.claim(
        lane_id="lane-retry",
        worker_id="w2",
        resources=("PATH:retry",),
        lease_seconds=10,
    )
    assert second is not None
    recover_lane_loss(
        registry=registry,
        lane_id="lane-retry",
        stale_fencing_token=second.fencing_token,
        stale_worker_id="w2",
    )
    third = registry.claim(
        lane_id="lane-retry",
        worker_id="w3",
        resources=("PATH:retry",),
        lease_seconds=10,
    )
    assert third is None
    incidents = registry.list_incidents("lane-retry")
    assert any(
        item.disposition == "BLOCKED_EXTERNAL" and item.reason == "RETRY_EXHAUSTED"
        for item in incidents
    )
    assert incidents[-1].disposition == "BLOCKED_EXTERNAL"
    assert incidents[-1].reason == "RETRY_EXHAUSTED"
    assert incidents[-1].retry_decision == "DENY"
    registry.close()


def test_owner_binding_rejects_foreign_renew_and_release(tmp_path: Path) -> None:
    registry = LaneRegistry(tmp_path / "lanes.sqlite3")
    lease = registry.claim(
        lane_id="lane-owner",
        worker_id="owner",
        resources=("PATH:owner",),
        lease_seconds=30,
    )
    assert lease is not None
    assert not registry.renew(
        lane_id="lane-owner",
        worker_id="intruder",
        fencing_token=lease.fencing_token,
    )
    assert not registry.release(
        lane_id="lane-owner",
        worker_id="intruder",
        fencing_token=lease.fencing_token,
    )
    assert registry.renew(
        lane_id="lane-owner",
        worker_id="owner",
        fencing_token=lease.fencing_token,
    )
    registry.close()


def test_result_receipt_immutability_and_idempotent_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "lanes.sqlite3"
    registry = LaneRegistry(db_path)
    lease = registry.claim(
        lane_id="lane-receipt",
        worker_id="worker-r",
        resources=("PATH:immutable",),
        lease_seconds=5,
    )
    assert lease is not None
    assert registry.record_result(
        lane_id="lane-receipt",
        worker_id="worker-r",
        fencing_token=lease.fencing_token,
        result_fingerprint="stable-receipt",
    )
    assert registry.record_result(
        lane_id="lane-receipt",
        worker_id="worker-r",
        fencing_token=lease.fencing_token,
        result_fingerprint="stable-receipt",
    )
    assert not registry.record_result(
        lane_id="lane-receipt",
        worker_id="worker-r",
        fencing_token=lease.fencing_token,
        result_fingerprint="mutated-receipt",
    )
    renamed = registry.claim(
        lane_id="lane-receipt-renamed",
        worker_id="worker-r2",
        resources=("PATH:immutable-other",),
        lease_seconds=5,
    )
    assert renamed is not None
    assert registry.result_for_attempt(lease.attempt_id)["result_fingerprint"] == "stable-receipt"
    assert registry.result_for_attempt(renamed.attempt_id) is None
    registry.close()
