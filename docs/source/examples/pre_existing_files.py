from __future__ import annotations

import logging
import sys
import time

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff, EmptyDirectorySnapshot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FileProcessingHandler(FileSystemEventHandler):
    def on_created(self, event: FileCreatedEvent) -> None:
        logger.info("Processing file: %s", event.src_path)


watched_directory = sys.argv[1] if len(sys.argv) > 1 else "."
event_handler = FileProcessingHandler()

# 1. Discover pre-existing files by diffing an empty snapshot against the current state
logger.info("Scanning for pre-existing files in %s...", watched_directory)
empty_snapshot = EmptyDirectorySnapshot()
current_snapshot = DirectorySnapshot(watched_directory, recursive=True)
initial_diff = DirectorySnapshotDiff(empty_snapshot, current_snapshot)

# 2. Replay created events for all pre-existing files before starting the live observer
for file_path in sorted(initial_diff.files_created):
    logger.info("Found pre-existing file: %s", file_path)
    event_handler.dispatch(FileCreatedEvent(file_path))

# 3. Start the live observer for subsequent file changes
observer = Observer()
observer.schedule(event_handler, watched_directory, recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
