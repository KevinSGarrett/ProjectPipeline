from __future__ import annotations

from multiprocessing import Process, Queue
from pathlib import Path
from time import sleep

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
    assert incident.state in {"RECOVERED", "HUMAN_REQUIRED"}
    reacquired = registry.claim(
        lane_id="lane-a-retry",
        worker_id="worker-a2",
        resources=("PATH:exclusive-a",),
        lease_seconds=5,
    )
    assert reacquired is not None
    registry.close()
