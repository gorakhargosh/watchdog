from __future__ import annotations

import errno
import logging
import os
import re
import time
from queue import Empty, Queue
from threading import Event
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers.api import ObservedWatch
from watchdog.observers.inotify import InotifyEmitter, InotifyObserver, InotifyWatchGroup
from watchdog.observers.inotify_c import (
    WATCHDOG_ALL_EVENTS,
    InotifyConstants,
    InotifyEvent,
    InotifyFD,
    Mask,
)
from watchdog.observers.inotify_move_event_grouper import PathedInotifyEvent

from .shell import mkdir, mkfile, mv

if TYPE_CHECKING:
    from .utils import P, StartWatching, TestEventQueue


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


def test_queue_events_when_inactive(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    watch = ObservedWatch(str(tmp_path), recursive=False)
    emitter = InotifyEmitter(Queue(), watch)
    # Simulate an emitter that has stopped or is inactive (_inotify is None).
    emitter._inotify = None  # noqa: SLF001

    caplog.set_level(logging.DEBUG)
    emitter.queue_events(0.01)

    error_logs = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert not error_logs, f"Unexpected error logs on inactive emitter: {error_logs}"
    assert any(
        record.levelno == logging.DEBUG and re.search(r"called when the thread is inactive", record.message)
        for record in caplog.records
    )


def _drain_event_queue(event_queue: TestEventQueue) -> list[FileSystemEvent]:
    events: list[FileSystemEvent] = []
    while True:
        try:
            events.append(event_queue.get_nowait()[0])
        except Empty:
            break
    return events


def _wait_until_sentinel(event_queue: TestEventQueue, sentinel_path: str) -> list[FileSystemEvent]:
    collected: list[FileSystemEvent] = []
    while True:
        ev = event_queue.get(timeout=5)[0]
        collected.append(ev)
        if isinstance(ev, FileCreatedEvent) and ev.src_path == sentinel_path:
            return collected


@pytest.mark.parametrize("use_full_emitter", [False, True])
def test_move_out_stops_watching(
    p: P,
    start_watching: StartWatching,
    event_queue: TestEventQueue,
    *,
    use_full_emitter: bool,
) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "sub"))
    mkdir(p("watched", "sub", "nested"))
    mkfile(p("watched", "sub", "nested", "file.txt"))
    mkdir(p("outside"))

    start_watching(path=p("watched"), use_full_emitter=use_full_emitter)

    mv(p("watched", "sub"), p("outside", "sub"))

    expected_paths = {p("watched", "sub"), p("watched", "sub", "nested")}
    seen_paths: set[str | bytes] = set()
    while not expected_paths.issubset(seen_paths):
        ev = event_queue.get(timeout=5)[0]
        if use_full_emitter:
            if isinstance(ev, DirMovedEvent) and ev.dest_path == "":
                seen_paths.add(ev.src_path)
        elif isinstance(ev, DirDeletedEvent):
            seen_paths.add(ev.src_path)

    _drain_event_queue(event_queue)

    # Modify files outside the watched tree, then flush with a sentinel inside watched/
    with open(p("outside", "sub", "nested", "file.txt"), "ab") as f:
        f.write(b"modified outside")
    mkfile(p("outside", "sub", "new_file.txt"))
    sentinel = p("watched", "_sentinel")
    mkfile(sentinel)

    after_events = _wait_until_sentinel(event_queue, sentinel)
    sub_prefix = p("watched", "sub")
    outside_prefix = p("outside")
    leaked = [
        e
        for e in after_events
        if os.path.commonpath([str(e.src_path), sub_prefix]) == sub_prefix
        or os.path.commonpath([str(e.src_path), outside_prefix]) == outside_prefix
    ]
    assert not leaked


def test_internal_move_preserves_watches(
    p: P,
    start_watching: StartWatching,
    event_queue: TestEventQueue,
) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "sub"))
    mkdir(p("watched", "sub", "nested"))
    mkfile(p("watched", "sub", "nested", "file.txt"))

    start_watching(path=p("watched"))

    mv(p("watched", "sub"), p("watched", "sub_new"))

    while True:
        ev = event_queue.get(timeout=5)[0]
        if (
            isinstance(ev, DirMovedEvent)
            and ev.src_path == p("watched", "sub")
            and ev.dest_path == p("watched", "sub_new")
        ):
            break

    _drain_event_queue(event_queue)

    target_file = p("watched", "sub_new", "nested", "file.txt")
    with open(target_file, "ab") as f:
        f.write(b"modified inside")
    sentinel = p("watched", "_sentinel")
    mkfile(sentinel)

    collected = _wait_until_sentinel(event_queue, sentinel)
    assert any(isinstance(e, FileModifiedEvent) and e.src_path == target_file for e in collected)


def test_move_out_buffered_events(
    p: P,
    event_queue: TestEventQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "sub"))
    mkfile(p("watched", "sub", "file.txt"))
    mkdir(p("outside"))

    sentinel_seen = Event()
    orig_on_event = InotifyWatchGroup.on_event

    def instrumented_on_event(self: InotifyWatchGroup, event: InotifyEvent) -> None:
        orig_on_event(self, event)
        if event.is_create and event.name and event.name.startswith(b"_sentinel"):
            sentinel_seen.set()

    monkeypatch.setattr(InotifyWatchGroup, "on_event", instrumented_on_event)

    inotify_fd = InotifyFD()
    inotify_fd.start()
    emitter = InotifyEmitter(event_queue, ObservedWatch(p("watched"), recursive=True), inotify_fd=inotify_fd)
    emitter.on_thread_start()
    try:
        watch_group = emitter._inotify  # noqa: SLF001
        assert watch_group is not None
        dq = watch_group._move_event_grouper._queue  # noqa: SLF001

        # 1. Real kernel move-out; wait for sentinel so IN_MOVED_FROM is buffered in queue
        mv(p("watched", "sub"), p("outside", "sub"))
        mkfile(p("watched", "_sentinel_1"))
        assert sentinel_seen.wait(timeout=5)
        sentinel_seen.clear()

        # 2. Buffer an in-flight file modification event for sub's watch descriptor behind IN_MOVED_FROM
        sub_node = watch_group._find_node_by_path(os.fsencode(p("watched", "sub")))  # noqa: SLF001
        assert sub_node is not None
        watch_group._move_event_grouper.put_event(  # noqa: SLF001
            PathedInotifyEvent(
                InotifyEvent(sub_node.wd, InotifyConstants.IN_MODIFY, 0, b"file.txt"),
                os.fsencode(p("watched", "sub", "file.txt")),
            )
        )
        assert (
            dq.find(lambda it: isinstance(it, PathedInotifyEvent) and it.ev.is_modify and it.ev.name == b"file.txt")
            is not None
        )

        dq.delay = 0
        while dq._queue:  # noqa: SLF001
            emitter.queue_events(0)

        events = _drain_event_queue(event_queue)
        assert any(isinstance(e, DirDeletedEvent) and e.src_path == p("watched", "sub") for e in events)
        assert not any(
            isinstance(e, FileModifiedEvent) and e.src_path == p("watched", "sub", "file.txt") for e in events
        )
    finally:
        emitter.on_thread_stop()
        inotify_fd.stop()
        inotify_fd.join(timeout=5)
        assert not inotify_fd.is_alive()


def test_move_out_and_back(p: P, event_queue: TestEventQueue) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "sub"))
    mkfile(p("watched", "sub", "file.txt"))

    # Unstarted InotifyFD so only explicit inotify_fd.handle_event() calls drive state transitions
    inotify_fd = InotifyFD()
    emitter = InotifyEmitter(event_queue, ObservedWatch(p("watched"), recursive=True), inotify_fd=inotify_fd)
    emitter.on_thread_start()
    try:
        watch_group = emitter._inotify  # noqa: SLF001
        assert watch_group is not None
        dq = watch_group._move_event_grouper._queue  # noqa: SLF001
        root_wd = watch_group._active_callbacks_by_path[os.fsencode(p("watched"))]  # noqa: SLF001
        sub_bytes = os.fsencode(p("watched", "sub"))

        # Dispatch departure (cookie=1) followed by re-entry (cookie=2) through InotifyFD
        inotify_fd.handle_event(
            InotifyEvent(root_wd, Mask(InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR), 1, b"sub")
        )
        inotify_fd.handle_event(
            InotifyEvent(root_wd, Mask(InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR), 2, b"sub")
        )

        with watch_group._lock, inotify_fd._lock:  # noqa: SLF001
            node_before = watch_group._find_node_by_path(sub_bytes)  # noqa: SLF001
            assert node_before is not None
            watch_before = inotify_fd._watch_for_wd.get(node_before.wd)  # noqa: SLF001
            assert watch_before is not None
            assert watch_group._id in watch_before.callbacks  # noqa: SLF001

        # Drain queued events after delay expires
        dq.delay = 0
        while dq._queue:  # noqa: SLF001
            emitter.queue_events(0)
        _drain_event_queue(event_queue)

        # The directory watch and callback registration must survive expiry of the original departure
        with watch_group._lock, inotify_fd._lock:  # noqa: SLF001
            restored_node = watch_group._find_node_by_path(sub_bytes)  # noqa: SLF001
            assert restored_node is not None
            assert watch_group._nodes_by_wd.get(restored_node.wd) is restored_node  # noqa: SLF001
            watch_after = inotify_fd._watch_for_wd.get(restored_node.wd)  # noqa: SLF001
            assert watch_after is not None
            assert watch_group._id in watch_after.callbacks  # noqa: SLF001

        inotify_fd.handle_event(InotifyEvent(restored_node.wd, Mask(InotifyConstants.IN_MODIFY), 0, b"file.txt"))
        emitter.queue_events(0)

        events = _drain_event_queue(event_queue)
        assert any(isinstance(e, FileModifiedEvent) and e.src_path == p("watched", "sub", "file.txt") for e in events)
    finally:
        emitter.on_thread_stop()
        inotify_fd.stop()
        if inotify_fd.is_alive():
            inotify_fd.join(timeout=5)
        assert not inotify_fd.is_alive()


def test_unrelated_create_during_pending_move(p: P, event_queue: TestEventQueue) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "dir_a"))
    mkdir(p("watched", "dir_a", "nested"))
    mkfile(p("watched", "dir_a", "nested", "file.txt"))

    inotify_fd = InotifyFD()
    emitter = InotifyEmitter(event_queue, ObservedWatch(p("watched"), recursive=True), inotify_fd=inotify_fd)
    emitter.on_thread_start()
    try:
        watch_group = emitter._inotify  # noqa: SLF001
        assert watch_group is not None
        dq = watch_group._move_event_grouper._queue  # noqa: SLF001
        root_wd = watch_group._active_callbacks_by_path[os.fsencode(p("watched"))]  # noqa: SLF001
        wd_a = watch_group._active_callbacks_by_path[os.fsencode(p("watched", "dir_a"))]  # noqa: SLF001
        wd_nested = watch_group._active_callbacks_by_path[os.fsencode(p("watched", "dir_a", "nested"))]  # noqa: SLF001

        mv(p("watched", "dir_a"), p("watched", "dir_a_new"))
        mkdir(p("watched", "dir_b"))

        # Pending move-from on dir_a, with an in-flight modification and an unrelated dir_b creation before move-to
        watch_group.on_event(
            InotifyEvent(root_wd, Mask(InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR), 10, b"dir_a")
        )
        watch_group.on_event(InotifyEvent(wd_nested, Mask(InotifyConstants.IN_MODIFY), 0, b"file.txt"))
        watch_group.on_event(
            InotifyEvent(root_wd, Mask(InotifyConstants.IN_CREATE | InotifyConstants.IN_ISDIR), 0, b"dir_b")
        )
        watch_group.on_event(
            InotifyEvent(root_wd, Mask(InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR), 10, b"dir_a_new")
        )

        dq.delay = 0
        while dq._queue:  # noqa: SLF001
            emitter.queue_events(0)
        events = _drain_event_queue(event_queue)

        with watch_group._lock:  # noqa: SLF001
            node_a = watch_group._find_node_by_path(os.fsencode(p("watched", "dir_a_new")))  # noqa: SLF001
            node_nested = watch_group._find_node_by_path(os.fsencode(p("watched", "dir_a_new", "nested")))  # noqa: SLF001
        assert node_a is not None
        assert node_a.wd == wd_a
        assert node_nested is not None
        assert node_nested.wd == wd_nested
        assert any(
            isinstance(e, FileModifiedEvent) and e.src_path == p("watched", "dir_a", "nested", "file.txt")
            for e in events
        )
    finally:
        emitter.on_thread_stop()
        inotify_fd.stop()
        if inotify_fd.is_alive():
            inotify_fd.join(timeout=5)
        assert not inotify_fd.is_alive()


@pytest.mark.parametrize(
    "event_filter",
    [
        [FileModifiedEvent],
        [FileCreatedEvent],
        [DirCreatedEvent],
        [DirModifiedEvent],
    ],
)
def test_recursive_filter_move_mask(event_filter: list[type[FileSystemEvent]]) -> None:
    watch = ObservedWatch("/tmp/dummy", recursive=True)
    emitter = InotifyEmitter(
        Queue(),  # type: ignore[arg-type]
        watch,
        event_filter=event_filter,
        inotify_fd=object(),  # type: ignore[arg-type]
    )
    mask = emitter.get_event_mask_from_filter()
    assert mask & InotifyConstants.IN_CREATE
    assert mask & InotifyConstants.IN_MOVE


def test_move_watches_replace_dest(p: P) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "dir_a"))
    mkdir(p("watched", "dir_a", "nested_a"))
    mkdir(p("watched", "dir_b"))
    mkdir(p("watched", "dir_b", "nested_b"))

    bytes_a = os.fsencode(p("watched", "dir_a"))
    bytes_nested_a = os.fsencode(p("watched", "dir_a", "nested_a"))
    bytes_b = os.fsencode(p("watched", "dir_b"))
    bytes_nested_b = os.fsencode(p("watched", "dir_b", "nested_b"))

    inotify_fd = InotifyFD()
    watch_group = InotifyWatchGroup(
        inotify_fd,
        os.fsencode(p("watched")),
        is_recursive=True,
        event_mask=WATCHDOG_ALL_EVENTS,
    )
    try:
        with watch_group._lock:  # noqa: SLF001
            node_a = watch_group._find_node_by_path(bytes_a)  # noqa: SLF001
            node_nested_a = watch_group._find_node_by_path(bytes_nested_a)  # noqa: SLF001
            wd_b = watch_group._active_callbacks_by_path[bytes_b]  # noqa: SLF001
            wd_nested_b = watch_group._active_callbacks_by_path[bytes_nested_b]  # noqa: SLF001
            assert node_a is not None
            assert node_nested_a is not None
            wd_a = node_a.wd
            wd_nested_a = node_nested_a.wd

            assert watch_group._move_watches(bytes_a, bytes_b)  # noqa: SLF001
            assert wd_b not in watch_group._nodes_by_wd  # noqa: SLF001
            assert wd_nested_b not in watch_group._nodes_by_wd  # noqa: SLF001
            assert watch_group._find_node_by_path(bytes_nested_b) is None  # noqa: SLF001
            assert watch_group._find_node_by_path(bytes_b) is node_a  # noqa: SLF001
            assert watch_group._find_node_by_path(os.fsencode(p("watched", "dir_b", "nested_a"))) is node_nested_a  # noqa: SLF001
        with inotify_fd._lock:  # noqa: SLF001
            for old_wd in (wd_b, wd_nested_b):
                watch_old = inotify_fd._watch_for_wd.get(old_wd)  # noqa: SLF001
                assert watch_old is None or watch_group._id not in watch_old.callbacks  # noqa: SLF001
            for kept_wd in (wd_a, wd_nested_a):
                watch_kept = inotify_fd._watch_for_wd.get(kept_wd)  # noqa: SLF001
                assert watch_kept is not None
                assert watch_group._id in watch_kept.callbacks  # noqa: SLF001
    finally:
        watch_group.deactivate()
        inotify_fd.stop()
        if inotify_fd.is_alive():
            inotify_fd.join(timeout=5)
        assert not inotify_fd.is_alive()


def test_external_move_over_existing_directory(
    p: P,
    start_watching: StartWatching,
    event_queue: TestEventQueue,
) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "dest"))
    mkdir(p("outside"))
    mkdir(p("outside", "src"))

    start_watching(path=p("watched"))
    _drain_event_queue(event_queue)

    # Move external directory over the watched destination directory
    mv(p("outside", "src"), p("watched", "dest"))

    # Create a new subdirectory inside the replacement directory
    mkdir(p("watched", "dest", "new_child"))
    sentinel = p("watched", "_sentinel")
    mkfile(sentinel)

    after_events = _wait_until_sentinel(event_queue, sentinel)
    assert any(isinstance(e, DirCreatedEvent) and e.src_path == p("watched", "dest", "new_child") for e in after_events)


def test_paired_move_preserved_when_source_dir_moved_out(
    p: P,
    event_queue: TestEventQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mkdir(p("watched"))
    mkdir(p("watched", "dir_a"))
    mkdir(p("watched", "dir_b"))
    mkfile(p("watched", "dir_a", "file.txt"))
    mkdir(p("outside"))

    sentinel_seen = Event()
    orig_on_event = InotifyWatchGroup.on_event

    def instrumented_on_event(self: InotifyWatchGroup, event: InotifyEvent) -> None:
        orig_on_event(self, event)
        if event.is_create and event.name and event.name.startswith(b"_sentinel"):
            sentinel_seen.set()

    monkeypatch.setattr(InotifyWatchGroup, "on_event", instrumented_on_event)

    inotify_fd = InotifyFD()
    inotify_fd.start()
    emitter = InotifyEmitter(event_queue, ObservedWatch(p("watched"), recursive=True), inotify_fd=inotify_fd)
    emitter.on_thread_start()
    try:
        watch_group = emitter._inotify  # noqa: SLF001
        assert watch_group is not None
        dq = watch_group._move_event_grouper._queue  # noqa: SLF001

        # 1. Move file from dir_a to dir_b (paired move within watched root)
        mv(p("watched", "dir_a", "file.txt"), p("watched", "dir_b", "file.txt"))
        mkfile(p("watched", "_sentinel_1"))
        assert sentinel_seen.wait(timeout=5)
        sentinel_seen.clear()

        # Deterministically verify that the paired move is buffered in the move grouper queue
        def _is_paired_file_move(it: object) -> bool:
            return not isinstance(it, PathedInotifyEvent) and it[1].path.endswith(b"file.txt")

        assert dq.find(_is_paired_file_move) is not None

        # 2. Move dir_a outside while the paired move from dir_a is buffered
        mv(p("watched", "dir_a"), p("outside", "dir_a"))
        mkfile(p("watched", "_sentinel_2"))
        assert sentinel_seen.wait(timeout=5)

        # 3. Drain queued events after delay expires
        dq.delay = 0
        while dq._queue:  # noqa: SLF001
            emitter.queue_events(0)

        events = _drain_event_queue(event_queue)
        assert any(
            isinstance(e, FileMovedEvent)
            and e.src_path == p("watched", "dir_a", "file.txt")
            and e.dest_path == p("watched", "dir_b", "file.txt")
            for e in events
        )
        assert any(isinstance(e, DirDeletedEvent) and e.src_path == p("watched", "dir_a") for e in events)
    finally:
        emitter.on_thread_stop()
        inotify_fd.stop()
        inotify_fd.join(timeout=5)
        assert not inotify_fd.is_alive()
