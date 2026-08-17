from __future__ import annotations

from multiprocessing import Process, Queue
from pathlib import Path
from time import sleep

import pytest

from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.recovery import recover_lane_loss


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
        fencing_token=lane_b.fencing_token,
        result_fingerprint="ok-lane-b",
    )
    assert not registry.record_result(
        lane_id="lane-a",
        fencing_token="stale-token",
        result_fingerprint="should-fail",
    )
    registry.close()


def test_worker_loss_recovery_and_reclaim(tmp_path: Path) -> None:
    db_path = tmp_path / "lanes.sqlite3"
    registry = LaneRegistry(db_path)
    lease = registry.claim(
        lane_id="lane-a",
        worker_id="worker-a",
        resources=("PATH:exclusive-a",),
        lease_seconds=1,
    )
    assert lease is not None
    sleep(1.2)
    incident = recover_lane_loss(
        registry=registry,
        lane_id="lane-a",
        stale_fencing_token=lease.fencing_token,
    )
    assert incident.state == "RECOVERED"
    assert incident.reason == "LEASE_RELEASED"
    assert not registry.record_result(
        lane_id="lane-a",
        fencing_token=lease.fencing_token,
        result_fingerprint="stale-result",
    )
    reacquired = registry.claim(
        lane_id="lane-a-retry",
        worker_id="worker-a2",
        resources=("PATH:exclusive-a",),
        lease_seconds=5,
    )
    assert reacquired is not None
    assert registry.record_result(
        lane_id="lane-a-retry",
        fencing_token=reacquired.fencing_token,
        result_fingerprint="replacement-result",
    )
    assert not registry.record_result(
        lane_id="lane-a-retry",
        fencing_token=reacquired.fencing_token,
        result_fingerprint="conflicting-replacement-result",
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
        fencing_token=lease.fencing_token,
        result_fingerprint="stable-receipt",
    )
    assert registry.record_result(
        lane_id="lane-receipt",
        fencing_token=lease.fencing_token,
        result_fingerprint="stable-receipt",
    )
    assert not registry.record_result(
        lane_id="lane-receipt",
        fencing_token=lease.fencing_token,
        result_fingerprint="mutated-receipt",
    )
    registry.close()
