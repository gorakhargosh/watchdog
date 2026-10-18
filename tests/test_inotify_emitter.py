from __future__ import annotations

from queue import Queue

import pytest

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

from watchdog.events import FileDeletedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers.inotify import InotifyObserver


@pytest.mark.parametrize("recursive", [True, False])
@pytest.mark.parametrize("create_after_start", [True, False])
def test_filtered_events_in_subdirectory(tmp_path, recursive, create_after_start):
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            events.put(event)

    directory = tmp_path / "subdirectory"
    ready = tmp_path / "ready"
    finished = tmp_path / "finished"
    ready.touch()
    finished.touch()
    if not create_after_start:
        directory.mkdir()

    observer = InotifyObserver()
    observer.schedule(
        Handler(),
        str(tmp_path),
        recursive=recursive,
        event_filter=[FileMovedEvent, FileDeletedEvent],
    )
    try:
        observer.start()
        if create_after_start:
            directory.mkdir()

        # The root deletion follows mkdir on the same inotify descriptor, so
        # receiving it also waits for registration of the new directory watch.
        ready.unlink()
        assert events.get(timeout=5) == FileDeletedEvent(str(ready))

        source = directory / "source"
        destination = directory / "destination"
        source.touch()
        source.rename(destination)
        destination.unlink()
        finished.unlink()

        if recursive:
            assert events.get(timeout=5) == FileMovedEvent(str(source), str(destination))
            assert events.get(timeout=5) == FileDeletedEvent(str(destination))
        # This second root event waits for the preceding operations and also
        # checks that the filter excluded their create/modify/open/close events.
        assert events.get(timeout=5) == FileDeletedEvent(str(finished))
        assert events.empty()
    finally:
        observer.stop()
        observer.join(timeout=5)
        assert not observer.is_alive()
