"""Consume watched filesystem events from an asyncio event loop.

The observer calls event handlers on its own thread, while an
:class:`asyncio.Queue` may only be used from the event loop thread. Handing
each event to the loop bridges the two, so asynchronous code can ``await``
filesystem events like any other source of work.

Usage::

    python asyncio_integration.py [path]

The directory to watch defaults to the current directory.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")


class AsyncioEventHandler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[FileSystemEvent]) -> None:
        self.loop = loop
        self.queue = queue

    def on_any_event(self, event: FileSystemEvent) -> None:
        # Runs on the observer thread, where the queue cannot be touched safely.
        # Let the event loop perform the put on its own thread instead.
        self.loop.call_soon_threadsafe(self.queue.put_nowait, event)


async def watch(path: str) -> None:
    """Log every filesystem event, awaiting them as the observer reports them."""
    queue: asyncio.Queue[FileSystemEvent] = asyncio.Queue()
    event_handler = AsyncioEventHandler(asyncio.get_running_loop(), queue)

    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            event = await queue.get()
            logging.info("Received %s", event)
    finally:
        observer.stop()
        observer.join()


path = sys.argv[1] if len(sys.argv) > 1 else "."

asyncio.run(watch(path))
