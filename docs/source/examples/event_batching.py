from __future__ import annotations

import logging
import sys
import time
from queue import Empty, Queue
from threading import Event, Thread

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO)


class BatchEventHandler(FileSystemEventHandler):
    """Collect filesystem events and process them in batches."""

    def __init__(self, batch_size: int = 10, flush_interval: float = 2.0) -> None:
        self.queue: Queue[FileSystemEvent] = Queue()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.stop_event = Event()
        self.worker = Thread(target=self._process_batches, daemon=True)
        self.worker.start()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.queue.put(event)

    def _process_batches(self) -> None:
        batch: list[FileSystemEvent] = []

        while not self.stop_event.is_set():
            try:
                event = self.queue.get(timeout=self.flush_interval)
                batch.append(event)

                if len(batch) >= self.batch_size:
                    self._handle_batch(batch)
                    batch = []
            except Empty:
                if batch:
                    self._handle_batch(batch)
                    batch = []

    def _handle_batch(self, batch: list[FileSystemEvent]) -> None:
        logging.info("Processing batch of %d filesystem events", len(batch))
        for event in batch:
            logging.info("  %s: %s", event.event_type, event.src_path)

    def stop(self) -> None:
        self.stop_event.set()
        self.worker.join()


path = sys.argv[1] if len(sys.argv) > 1 else "."

event_handler = BatchEventHandler(batch_size=10, flush_interval=2)
observer = Observer()
observer.schedule(event_handler, path, recursive=True)
observer.start()

try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    event_handler.stop()
    observer.join()
