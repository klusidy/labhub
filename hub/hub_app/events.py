from __future__ import annotations
import asyncio
from typing import Any, Dict, List


class EventBus:
    """Very small pub-sub for broadcasting JSON-serializable events to WS clients."""

    def __init__(self) -> None:
        self._subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    async def publish(self, event: Dict[str, Any]) -> None:
        dead: List[asyncio.Queue] = []
        async with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop oldest to make room (preview semantics)
                    try:
                        _ = q.get_nowait()
                        await q.put(event)
                    except Exception:
                        dead.append(q)
            for q in dead:
                if q in self._subscribers:
                    self._subscribers.remove(q)
