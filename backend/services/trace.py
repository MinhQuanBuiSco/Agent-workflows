"""Event log for one review run, so the desk can watch the agent work.

A review runs as a background task. It does not belong to the HTTP request
that started it: closing the tab no longer cancels the model call. Every step
is appended to the run's log, and any number of readers can replay the log
from the start and then follow it live.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

KEEPALIVE_SECONDS = 15
DELTA_FLUSH_SECONDS = 0.1


class Run:
    def __init__(self, matter_id: str, mode: str) -> None:
        self.matter_id = matter_id
        self.mode = mode
        self.events: list[dict[str, Any]] = []
        self.done = False
        self.task: asyncio.Task | None = None
        self._started = time.monotonic()
        self._changed = asyncio.Event()
        self._delta_call: str | None = None
        self._delta_parts: list[str] = []
        self._delta_at = 0.0

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def emit(self, kind: str, **data: Any) -> None:
        self._flush_delta()
        self._append(kind, data)

    async def delta(self, call: str, text: str) -> None:
        """Model tokens arrive one at a time. Batch them so the log stays small."""
        if self._delta_call not in (None, call):
            self._flush_delta()
        self._delta_call = call
        self._delta_parts.append(text)
        now = time.monotonic()
        if now - self._delta_at >= DELTA_FLUSH_SECONDS:
            self._flush_delta()
            self._delta_at = now
        # Yield so the reader can send what is buffered while the model runs.
        await asyncio.sleep(0)

    def finish(self) -> None:
        self._flush_delta()
        self.done = True
        self._wake()

    def _flush_delta(self) -> None:
        if self._delta_parts and self._delta_call:
            self._append(
                "model_delta", {"call": self._delta_call, "text": "".join(self._delta_parts)}
            )
        self._delta_parts = []
        self._delta_call = None

    def _append(self, kind: str, data: dict[str, Any]) -> None:
        self.events.append({"seq": len(self.events), "t": self.elapsed_ms(), "type": kind, **data})
        self._wake()

    def _wake(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()


class TraceHub:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def clear(self) -> None:
        self._runs.clear()

    def get(self, matter_id: str) -> Run | None:
        return self._runs.get(matter_id)

    def running(self, matter_id: str) -> Run | None:
        run = self._runs.get(matter_id)
        return run if run is not None and not run.done else None

    def start(self, matter_id: str, mode: str, work: Callable[[Run], Awaitable[None]]) -> Run:
        run = Run(matter_id, mode)
        self._runs[matter_id] = run

        async def body() -> None:
            try:
                await work(run)
            finally:
                run.finish()

        run.task = asyncio.create_task(body())
        return run

    async def follow(self, run: Run, after: int = -1) -> AsyncIterator[dict[str, Any]]:
        """Replay events after seq `after`, then stream new ones until the run ends."""
        index = after + 1
        # Not logged: tells a reader who joins late how long the run has been going.
        yield {"type": "clock", "t": run.elapsed_ms(), "done": run.done}
        while True:
            while index < len(run.events):
                yield run.events[index]
                index += 1
            if run.done:
                return
            changed = run._changed
            try:
                await asyncio.wait_for(changed.wait(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield {"type": "keepalive"}


hub = TraceHub()
