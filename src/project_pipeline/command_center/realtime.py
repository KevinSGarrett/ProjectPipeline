from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from threading import RLock

from project_pipeline.command_center.models import TimelinePage
from project_pipeline.contracts import EventEnvelope


class RealtimeEventBroker:
    """Replayable projection event broker. EventEnvelope remains the canonical internal event contract."""

    def __init__(self, *, retention: int = 2000) -> None:
        if retention < 1:
            raise ValueError("retention must be positive")
        self.retention = retention
        self._events: deque[EventEnvelope] = deque(maxlen=retention)
        self._next_sequence = 1
        self._lock = RLock()
        self._subscribers: set[asyncio.Queue[EventEnvelope]] = set()

    def publish(self, event: EventEnvelope) -> EventEnvelope:
        with self._lock:
            assigned = event.model_copy(update={"sequence": self._next_sequence})
            self._next_sequence += 1
            self._events.append(assigned)
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(assigned)
            except asyncio.QueueFull:
                continue
        return assigned

    def page(self, *, after_sequence: int = 0, limit: int = 200) -> TimelinePage:
        if after_sequence < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid replay cursor or limit")
        with self._lock:
            matching = [x for x in self._events if x.sequence > after_sequence]
        page = matching[:limit]
        next_sequence = page[-1].sequence if page else after_sequence
        return TimelinePage(
            after_sequence=after_sequence,
            next_sequence=next_sequence,
            has_more=len(matching) > limit,
            events=tuple(page),
        )

    async def subscribe(
        self, *, after_sequence: int = 0, queue_size: int = 256
    ) -> AsyncIterator[EventEnvelope]:
        for event in self.page(after_sequence=after_sequence, limit=1000).events:
            yield event
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=queue_size)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    @staticmethod
    def sse(event: EventEnvelope) -> str:
        data = json.dumps(event.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data}\n\n"
