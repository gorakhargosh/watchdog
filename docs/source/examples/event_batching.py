"""
Event Batching / Coalescing
============================

This example demonstrates how to batch and debounce filesystem events so that
rapid bursts of changes (e.g., a build tool touching many files at once) are
processed as a single logical event rather than flooding the handler.

A background worker thread drains a queue every ``DEBOUNCE_INTERVAL`` seconds
and processes all accumulated events together.

Use-cases
---------
* Triggering a test run or build only once after a save-storm.
* Aggregating log-file rotations before processing.
* Reducing redundant API calls when watching config files.
"""

import logging
import queue
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# How long (seconds) to wait after the last event before processing the batch.
DEBOUNCE_INTERVAL = 1.0

# Directory to watch — change this to any path you like.
WATCH_PATH = "."


class BatchingEventHandler(FileSystemEventHandler):
    """Collects filesystem events into a queue for deferred batch processing."""

    def __init__(self, event_queue: queue.Queue) -> None:
        super().__init__()
        self._queue = event_queue

    def on_any_event(self, event: FileSystemEvent) -> None:
        # Skip directory events — focus on file changes.
        if event.is_directory:
            return
        self._queue.put(event)


def batch_worker(event_queue: queue.Queue, stop_event: threading.Event) -> None:
    """
    Background worker that drains the queue in DEBOUNCE_INTERVAL-second windows.

    Waits until the queue has been idle for DEBOUNCE_INTERVAL seconds, then
    processes all accumulated events as a single batch.
    """
    pending: list[FileSystemEvent] = []

    while not stop_event.is_set():
        try:
            # Block until the first event arrives (or stop is requested).
            event = event_queue.get(timeout=DEBOUNCE_INTERVAL)
            pending.append(event)

            # Drain any additional events that arrive within the debounce window.
            deadline = time.monotonic() + DEBOUNCE_INTERVAL
            while time.monotonic() < deadline:
                try:
                    extra = event_queue.get_nowait()
                    pending.append(extra)
                    # Reset the deadline on each new arrival.
                    deadline = time.monotonic() + DEBOUNCE_INTERVAL
                except queue.Empty:
                    time.sleep(0.05)

            # --- Process the batch ---
            process_batch(pending)
            pending.clear()

        except queue.Empty:
            # No events arrived during the timeout — just loop.
            continue


def process_batch(events: list[FileSystemEvent]) -> None:
    """
    Called once per coalesced batch of filesystem events.

    Replace the body of this function with your own logic, e.g.
    running pytest, triggering a build, or sending a webhook.
    """
    # Deduplicate by (event type, src_path) so that repeated modify
    # events on the same file are counted only once.
    seen: set[tuple[str, str]] = set()
    unique_events = []
    for evt in events:
        key = (evt.event_type, evt.src_path)
        if key not in seen:
            seen.add(key)
            unique_events.append(evt)

    logger.info(
        "Batch ready — %d raw event(s), %d unique after dedup:",
        len(events),
        len(unique_events),
    )
    for evt in unique_events:
        logger.info("  [%s] %s", evt.event_type.upper(), Path(evt.src_path).name)

    # TODO: add your build / test / notification logic here.


def main() -> None:
    event_queue: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    handler = BatchingEventHandler(event_queue)
    observer = Observer()
    observer.schedule(handler, path=WATCH_PATH, recursive=True)

    worker_thread = threading.Thread(
        target=batch_worker,
        args=(event_queue, stop_event),
        name="BatchWorker",
        daemon=True,
    )

    logger.info("Watching '%s' (Ctrl-C to stop) …", Path(WATCH_PATH).resolve())
    observer.start()
    worker_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping …")
    finally:
        stop_event.set()
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
