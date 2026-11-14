from __future__ import annotations

import logging
import sys
import time
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from collections.abc import Callable

    from watchdog.events import FileSystemEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CallableEventHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[FileSystemEvent], None]) -> None:
        super().__init__()
        self._callback = callback

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._callback(event)


event_handler = CallableEventHandler(lambda event: logger.info("%s", event))
observer = Observer()
observer.schedule(event_handler, sys.argv[1] if len(sys.argv) > 1 else ".", recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
