import asyncio

from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.contracts import EventEnvelope


def event(n):
    return EventEnvelope(
        event_id=f"event:test:{n}",
        event_type="work.changed",
        project_id="PROJ-TEST",
        producer="test",
        correlation_id="corr:test",
        aggregate_type="task",
        aggregate_id=f"task:{n}",
        payload={"n": n},
    )


def test_sequence_and_reconnect_replay():
    b = RealtimeEventBroker(retention=10)
    e1 = b.publish(event(1))
    e2 = b.publish(event(2))
    e3 = b.publish(event(3))
    assert (e1.sequence, e2.sequence, e3.sequence) == (1, 2, 3)
    page = b.page(after_sequence=1)
    assert [x.event_id for x in page.events] == [e2.event_id, e3.event_id]
    assert page.next_sequence == 3


def test_retention_bounds_replay():
    b = RealtimeEventBroker(retention=2)
    for n in range(1, 5):
        b.publish(event(n))
    assert [x.sequence for x in b.page().events] == [3, 4]


def test_sse_contains_cursor_event_and_json():
    b = RealtimeEventBroker()
    e = b.publish(event(1))
    wire = b.sse(e)
    assert "id: 1" in wire and "event: work.changed" in wire and '"sequence":1' in wire


def test_live_subscription_gets_future_event():
    async def run():
        b = RealtimeEventBroker()
        stream = b.subscribe()
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        published = b.publish(event(1))
        observed = await asyncio.wait_for(task, 1)
        await stream.aclose()
        return published, observed

    published, observed = asyncio.run(run())
    assert observed.event_id == published.event_id
