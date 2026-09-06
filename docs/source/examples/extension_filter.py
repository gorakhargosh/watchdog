"""Monitor only selected file extensions."""

from pathlib import Path
import sys
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


WATCHED_EXTENSIONS = {".csv", ".xlsx"}


class ExtensionFilterHandler(FileSystemEventHandler):
    """Print events only for files with selected extensions."""

    def _is_watched_file(self, path: str) -> bool:
        return Path(path).suffix.lower() in WATCHED_EXTENSIONS

    def on_created(self, event) -> None:
        if not event.is_directory and self._is_watched_file(event.src_path):
            print(f"Created: {event.src_path}")

    def on_modified(self, event) -> None:
        if not event.is_directory and self._is_watched_file(event.src_path):
            print(f"Modified: {event.src_path}")

    def on_deleted(self, event) -> None:
        if not event.is_directory and self._is_watched_file(event.src_path):
            print(f"Deleted: {event.src_path}")


def main() -> None:
    """Watch a directory for selected file types."""
    path = sys.argv[1] if len(sys.argv) > 1 else "."

    event_handler = ExtensionFilterHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()

    print(f"Watching {path} for: {', '.join(sorted(WATCHED_EXTENSIONS))}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
