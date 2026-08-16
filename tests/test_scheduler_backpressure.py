from project_pipeline.domain.scheduler import BackpressureSignals
from project_pipeline.scheduler import evaluate_backpressure


def test_backpressure_modes_are_monotonic() -> None:
    assert evaluate_backpressure(BackpressureSignals(queue_depth=0)).mode.value == "NORMAL"
    assert evaluate_backpressure(BackpressureSignals(queue_depth=50)).mode.value == "CONGESTED"
    assert evaluate_backpressure(BackpressureSignals(queue_depth=200)).mode.value == "BROWNOUT"
    assert (
        evaluate_backpressure(BackpressureSignals(queue_depth=1000)).mode.value == "HALT_NEW_WORK"
    )


def test_memory_and_disk_pressure_can_halt_admission() -> None:
    assert (
        evaluate_backpressure(BackpressureSignals(memory_used_percent=98)).mode.value
        == "HALT_NEW_WORK"
    )
    assert (
        evaluate_backpressure(BackpressureSignals(disk_free_percent=2)).mode.value
        == "HALT_NEW_WORK"
    )
