"""Organize files in a watched directory into category subfolders.

When a new file appears in the watched directory it is immediately moved
into a subfolder based on its file extension (for example ``.png`` files
are moved into ``images/`` and ``.mp4`` files into ``videos/``).

Usage::

    python file_organizer.py [path]

The directory to watch defaults to the current directory.
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

#: Map a file extension to the subfolder it should be moved into.
CATEGORIES = {
    ".gif": "images",
    ".jpeg": "images",
    ".jpg": "images",
    ".png": "images",
    ".mkv": "videos",
    ".mov": "videos",
    ".mp4": "videos",
    ".docx": "documents",
    ".pdf": "documents",
    ".txt": "documents",
}


class FileOrganizerHandler(FileSystemEventHandler):
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        source = Path(event.src_path)
        category = CATEGORIES.get(source.suffix.lower(), "misc")
        target_dir = self.base_dir / category
        target_dir.mkdir(exist_ok=True)
        target = target_dir / source.name
        counter = 1
        while target.exists():
            target = target_dir / f"{source.stem}_{counter}{source.suffix}"
            counter += 1
        shutil.move(str(source), str(target))
        logging.info("Moved %s -> %s", source.name, target)


path = sys.argv[1] if len(sys.argv) > 1 else "."
base_dir = Path(path).resolve()

event_handler = FileOrganizerHandler(base_dir)
observer = Observer()
observer.schedule(event_handler, str(base_dir), recursive=False)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
