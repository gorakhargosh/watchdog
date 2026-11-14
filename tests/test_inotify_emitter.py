from __future__ import annotations

import errno
import os
import time
from queue import Queue
from threading import Event

import pytest

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers.inotify import InotifyObserver, InotifyWatchGroup
from watchdog.observers.inotify_c import InotifyFD


def test_observer_does_not_initialize_shared_inotify_fd(monkeypatch):
    # monkeypatch restores the session fixture's shared instance after the test.
    monkeypatch.setattr(InotifyFD, "_instance", None)
    observer = InotifyObserver()
    try:
        assert InotifyFD._instance is None  # noqa: SLF001
    finally:
        observer.stop()


@pytest.mark.parametrize("running", [False, True])
def test_empty_observers_do_not_allocate_inotify_resources(monkeypatch, running):
    def unexpected_allocation():
        raise AssertionError("An observer without watches must not allocate an inotify instance")

    monkeypatch.setattr(InotifyFD, "_create_inotify_fd", staticmethod(unexpected_allocation))
    observers = []
    try:
        for _ in range(5):
            observer = InotifyObserver()
            observers.append(observer)
            if running:
                observer.start()
    finally:
        for observer in observers:
            observer.stop()
            if observer.is_alive():
                observer.join(timeout=5)


def test_observers_have_independent_inotify_fds(tmp_path):
    observers = []
    try:
        observers.extend(InotifyObserver() for _ in range(2))
        for observer in observers:
            observer.schedule(FileSystemEventHandler(), tmp_path)

        first, second = (observer._inotify_fd for observer in observers)  # noqa: SLF001
        assert first is not second
        assert first._inotify_fd != second._inotify_fd  # noqa: SLF001
        assert first.is_alive()
        assert second.is_alive()

        observers[0].stop()
        assert not first.is_alive()
        assert second.is_alive()
    finally:
        for observer in observers:
            observer.stop()
        assert all(not observer._inotify_fd.is_alive() for observer in observers)  # noqa: SLF001


@pytest.mark.parametrize("generate_full_events", [True, False])
def test_observer_delivers_created_events(tmp_path, generate_full_events):
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_created(self, event):
            events.put(event)

    observer = InotifyObserver(generate_full_events=generate_full_events)
    directories = [tmp_path / "first", tmp_path / "second"]
    try:
        for directory in directories:
            directory.mkdir()
            observer.schedule(Handler(), directory)
        assert all(emitter._inotify_fd is observer._inotify_fd for emitter in observer.emitters)  # noqa: SLF001
        observer.start()

        for directory in directories:
            marker = directory / "marker"
            marker.touch()
            assert events.get(timeout=5) == FileCreatedEvent(str(marker))
    finally:
        observer.stop()
        if observer.is_alive():
            observer.join(timeout=5)
        assert not observer.is_alive()
        assert not observer._inotify_fd.is_alive()  # noqa: SLF001


@pytest.mark.parametrize("recursive", [True, False])
@pytest.mark.parametrize("running", [True, False])
def test_missing_root_raises_and_can_be_retried(tmp_path, recursive, running):
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            events.put(event)

    handler = Handler()
    directory = tmp_path / "root"
    directory.mkdir()
    observer = InotifyObserver()
    try:
        if running:
            observer.start()
        else:
            observer.schedule(handler, directory, recursive=recursive, event_filter=[FileDeletedEvent])

        # The directory must exist when the kernel watch is registered, even
        # if it existed when the watch was scheduled before observer.start().
        directory.rmdir()
        if running:
            with pytest.raises(FileNotFoundError) as exc:
                observer.schedule(handler, directory, recursive=recursive, event_filter=[FileDeletedEvent])
        else:
            with pytest.raises(FileNotFoundError) as exc:
                observer.start()
        assert exc.value.errno == errno.ENOENT
        assert not observer.emitters

        directory.mkdir()
        marker = directory / "marker"
        marker.touch()
        observer.schedule(handler, directory, recursive=recursive, event_filter=[FileDeletedEvent])
        if not running:
            observer.start()
        marker.unlink()
        assert events.get(timeout=5) == FileDeletedEvent(str(marker))
    finally:
        observer.stop()
        if observer.is_alive():
            observer.join(timeout=5)
        assert not observer.is_alive()


@pytest.mark.parametrize("error", [errno.ENOENT, errno.EACCES])
@pytest.mark.parametrize("create_after_start", [True, False])
def test_recursive_watch_ignores_subdirectory_errors(tmp_path, monkeypatch, error, create_after_start):
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            events.put(event)

    skipped = tmp_path / "skipped"
    watched = tmp_path / "watched"
    ready = tmp_path / "ready"
    ready.touch()
    if not create_after_start:
        skipped.mkdir()
        watched.mkdir()

    observer = InotifyObserver()
    observer.schedule(Handler(), tmp_path, recursive=True, event_filter=[DirCreatedEvent, FileDeletedEvent])
    inotify_fd = observer._inotify_fd  # noqa: SLF001
    add_callback = inotify_fd.add_callback
    registration_attempted = Event()

    def add_callback_with_error(path, *args, **kwargs):
        if path == os.fsencode(skipped):
            registration_attempted.set()
            raise OSError(error, os.strerror(error), path)
        return add_callback(path, *args, **kwargs)

    monkeypatch.setattr(inotify_fd, "add_callback", add_callback_with_error)
    try:
        observer.start()
        if create_after_start:
            skipped.mkdir()
            watched.mkdir()
            assert events.get(timeout=5) == DirCreatedEvent(str(skipped))
            assert events.get(timeout=5) == DirCreatedEvent(str(watched))

        # Receiving the root event waits for both subdirectory registrations.
        ready.unlink()
        assert events.get(timeout=5) == FileDeletedEvent(str(ready))
        assert registration_attempted.is_set()

        marker = watched / "marker"
        marker.touch()
        marker.unlink()
        assert events.get(timeout=5) == FileDeletedEvent(str(marker))
    finally:
        observer.stop()
        if observer.is_alive():
            observer.join(timeout=5)
        assert not observer.is_alive()


@pytest.mark.parametrize("error", [errno.ENOSPC, errno.EMFILE])
def test_recursive_watch_limit_on_subdirectory_reaches_caller(tmp_path, monkeypatch, error):
    skipped = tmp_path / "skipped"
    skipped.mkdir()

    observer = InotifyObserver()
    observer.schedule(FileSystemEventHandler(), tmp_path, recursive=True)
    inotify_fd = observer._inotify_fd  # noqa: SLF001
    add_callback = inotify_fd.add_callback

    def add_callback_with_error(path, *args, **kwargs):
        if path == os.fsencode(skipped):
            raise OSError(error, os.strerror(error), path)
        return add_callback(path, *args, **kwargs)

    monkeypatch.setattr(inotify_fd, "add_callback", add_callback_with_error)
    try:
        with pytest.raises(OSError, match=os.strerror(error)) as exc:
            observer.start()
        assert exc.value.errno == error
        assert not observer.emitters
    finally:
        observer.stop()
        if observer.is_alive():
            observer.join(timeout=5)


@pytest.mark.parametrize("error", [errno.ENOSPC, errno.EMFILE])
def test_recursive_watch_limit_on_new_subdirectory_is_logged(tmp_path, monkeypatch, caplog, error):
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            events.put(event)

    skipped = tmp_path / "skipped"
    ready = tmp_path / "ready"
    ready.touch()

    observer = InotifyObserver()
    observer.schedule(Handler(), tmp_path, recursive=True, event_filter=[DirCreatedEvent, FileDeletedEvent])
    inotify_fd = observer._inotify_fd  # noqa: SLF001
    add_callback = inotify_fd.add_callback

    def add_callback_with_error(path, *args, **kwargs):
        if path == os.fsencode(skipped):
            raise OSError(error, os.strerror(error), path)
        return add_callback(path, *args, **kwargs)

    monkeypatch.setattr(inotify_fd, "add_callback", add_callback_with_error)
    try:
        observer.start()
        skipped.mkdir()
        assert events.get(timeout=5) == DirCreatedEvent(str(skipped))

        # The observer keeps running and reports events from the root.
        ready.unlink()
        assert events.get(timeout=5) == FileDeletedEvent(str(ready))
        assert any(
            record.levelname == "WARNING" and os.strerror(error) in record.getMessage() for record in caplog.records
        )
    finally:
        observer.stop()
        if observer.is_alive():
            observer.join(timeout=5)
        assert not observer.is_alive()


def test_new_directory_filled_while_its_watches_are_added(tmp_path, monkeypatch):
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            events.put(event)

    tree = tmp_path / "tree"
    late = tree / "late"
    add_all_callbacks = InotifyWatchGroup._add_all_callbacks  # noqa: SLF001

    def add_all_callbacks_then_copy_more(self, path):
        add_all_callbacks(self, path)
        if path == os.fsencode(tree):
            # Like `cp -r` still copying: this appears after the watches for the new tree were added
            (late / "nested").mkdir(parents=True)
            (late / "file").touch()

    monkeypatch.setattr(InotifyWatchGroup, "_add_all_callbacks", add_all_callbacks_then_copy_more)
    observer = InotifyObserver()
    observer.schedule(
        Handler(), tmp_path, recursive=True, event_filter=[DirCreatedEvent, FileCreatedEvent, FileDeletedEvent]
    )
    try:
        observer.start()
        tree.mkdir()

        expected = {DirCreatedEvent(str(late / "nested")), FileCreatedEvent(str(late / "file"))}
        while expected:
            expected.discard(events.get(timeout=5))

        # The late directory is watched too
        marker = late / "nested" / "marker"
        marker.touch()
        marker.unlink()
        while events.get(timeout=5) != FileDeletedEvent(str(marker)):
            pass
    finally:
        observer.stop()
        observer.join(timeout=5)
        assert not observer.is_alive()


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


def test_schedule_unschedule_load(tmp_path):
    events = Queue()
    handler = FileSystemEventHandler()
    handler.on_any_event = events.put  # type: ignore[method-assign]
    subdirs = [tmp_path / f"sub_{i}" for i in range(6)]
    for d in subdirs:
        d.mkdir()

    observer = InotifyObserver()
    root_watch = observer.schedule(handler, str(tmp_path), recursive=True)
    observer.start()
    try:
        for cycle in range(15):
            extra = [observer.schedule(handler, str(d), recursive=True) for d in subdirs[:3]]
            for d in subdirs:
                f = d / f"f_{cycle}.txt"
                f.write_text("x")
                f.unlink()
            for w in extra:
                observer.unschedule(w)

        marker = tmp_path / "done.txt"
        marker.touch()
        marker.unlink()
        deadline = time.monotonic() + 5.0
        while True:
            remaining = max(0.01, deadline - time.monotonic())
            if events.get(timeout=remaining) == FileDeletedEvent(str(marker)):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Did not observe marker deletion within 5s")
        observer.unschedule(root_watch)
    finally:
        observer.stop()
        observer.join(timeout=5)
        assert not observer.is_alive()
