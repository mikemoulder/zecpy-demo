"""Fan-out of demo events to every connected browser, with a replay buffer so a page
opened mid-scene (or reloaded during a take) shows everything that happened."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator


class Hub:
    def __init__(self, keep: int = 2_000) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._history: list[str] = []
        self._keep = keep

    def publish(self, kind: str, **data: Any) -> None:
        line = json.dumps({"type": kind, "t": time.time(), **data}, default=str)
        self._history.append(line)
        del self._history[: -self._keep]
        for queue in self._subscribers:
            queue.put_nowait(line)

    def clear(self) -> None:
        self._history.clear()
        self.publish("reset")

    async def stream(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        for line in self._history:
            queue.put_nowait(line)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
