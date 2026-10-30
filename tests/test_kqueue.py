from __future__ import annotations

import pytest

from watchdog.utils import platform

if not platform.is_bsd() and not platform.is_darwin():
    pytest.skip("BSD/macOS only.", allow_module_level=True)

import errno
import os
from queue import Empty, Queue
from time import monotonic
from unittest.mock import patch

from watchdog.events import (
    DirAttribEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileAttribEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers.api import EventQueue, ObservedWatch
from watchdog.observers.kqueue import KqueueEmitter, KqueueObserver

pytestmark = pytest.mark.timeout(10)


@pytest.fixture
def make_emitter(tmp_path):
    emitters = []

    def make(*, recursive=True):
        event_queue = EventQueue()
        emitter = KqueueEmitter(event_queue, ObservedWatch(str(tmp_path), recursive=recursive), timeout=0.05)
        emitters.append(emitter)
        # Construction opens descriptors; control() installs them in the kernel.
        emitter.queue_events(0)
        assert event_queue.empty()
        return emitter, event_queue

    yield make

    for emitter in emitters:
        descriptors = emitter._descriptors  # noqa: SLF001
        fds = [descriptors.get(path).fd for path in descriptors.paths]
        with patch("os.close", wraps=os.close) as close:
            emitter.stop()
            if emitter.ident is not None:
                emitter.join(5)
        for fd in fds:
            close.assert_any_call(fd)
        assert not emitter.is_alive()
        assert emitter._kq.closed  # noqa: SLF001
        assert emitter._descriptors.paths == []  # noqa: SLF001
        assert emitter._descriptors.kevents == []  # noqa: SLF001


def collect_events(emitter, event_queue, *expected, timeout=3):
    """Drive complete read/bookkeeping cycles within one absolute deadline."""
    events = []
    deadline = monotonic() + timeout
    while (remaining := deadline - monotonic()) > 0:
        emitter.queue_events(min(0.05, remaining))
        while True:
            try:
                event, watch = event_queue.get_nowait()
            except Empty:
                break
            assert watch == emitter.watch
            events.append(event)
        if expected and set(expected).issubset(events):
            break
    assert set(expected).issubset(events), events
    return events


def test_idle_start_stop(make_emitter):
    emitter, event_queue = make_emitter()
    descriptors = emitter._descriptors  # noqa: SLF001
    fds = [descriptors.get(path).fd for path in descriptors.paths]
    assert collect_events(emitter, event_queue, timeout=0.1) == []
    emitter.start()
    with patch("os.close", wraps=os.close) as close:
        emitter.stop()
        emitter.join(5)
    for fd in fds:
        close.assert_any_call(fd)
    assert not emitter.is_alive()
    assert event_queue.empty()


def test_create_file_then_modify(tmp_path, make_emitter):
    emitter, event_queue = make_emitter()
    path = tmp_path / "created"
    path.write_text("first")
    collect_events(emitter, event_queue, FileCreatedEvent(str(path)), DirModifiedEvent(str(tmp_path)))
    # Install the newly created file's descriptor before the next operation.
    emitter.queue_events(0)
    mode = path.stat().st_mode
    try:
        path.chmod(mode ^ 0o100)
        collect_events(emitter, event_queue, FileAttribEvent(str(path)))
    finally:
        path.chmod(mode)
    with path.open("a") as stream:
        stream.write("second")
    collect_events(emitter, event_queue, FileModifiedEvent(str(path)))


def test_create_directory_then_child(tmp_path, make_emitter):
    emitter, event_queue = make_emitter()
    directory = tmp_path / "created"
    directory.mkdir()
    collect_events(emitter, event_queue, DirCreatedEvent(str(directory)), DirModifiedEvent(str(tmp_path)))
    emitter.queue_events(0)
    child = directory / "child"
    child.touch()
    collect_events(emitter, event_queue, FileCreatedEvent(str(child)), DirModifiedEvent(str(directory)))


def test_modify_existing_file(tmp_path, make_emitter):
    path = tmp_path / "existing"
    path.write_text("before")
    emitter, event_queue = make_emitter()
    with path.open("a") as stream:
        stream.write("after")
    events = collect_events(emitter, event_queue, FileModifiedEvent(str(path)))
    assert not any(isinstance(event, (FileAttribEvent, FileCreatedEvent, FileDeletedEvent)) for event in events)


@pytest.mark.parametrize("is_directory", [False, True])
def test_attribute_change(tmp_path, make_emitter, is_directory):
    path = tmp_path / "attributes"
    if is_directory:
        path.mkdir()
    else:
        path.touch()
    mode = path.stat().st_mode
    emitter, event_queue = make_emitter()
    event_type = DirAttribEvent if is_directory else FileAttribEvent
    try:
        path.chmod(mode ^ 0o100)
        events = collect_events(emitter, event_queue, event_type(str(path)))
        assert not any(isinstance(event, FileModifiedEvent) for event in events)
    finally:
        path.chmod(mode)


@pytest.mark.parametrize("is_directory", [False, True])
def test_delete_unregisters_descriptor(tmp_path, make_emitter, is_directory):
    path = tmp_path / "deleted"
    if is_directory:
        path.mkdir()
    else:
        path.touch()
    emitter, event_queue = make_emitter()
    descriptors = emitter._descriptors  # noqa: SLF001
    fd = descriptors.get(str(path)).fd
    if is_directory:
        path.rmdir()
    else:
        path.unlink()
    event_type = DirDeletedEvent if is_directory else FileDeletedEvent
    with patch("os.close", wraps=os.close) as close:
        collect_events(emitter, event_queue, event_type(str(path)))
    close.assert_any_call(fd)
    assert str(path) not in descriptors
    with pytest.raises(KeyError):
        descriptors.get_for_fd(fd)


@pytest.mark.parametrize("is_directory", [False, True])
@pytest.mark.parametrize("recursive", [False, True])
def test_rename_within_watch(tmp_path, make_emitter, is_directory, recursive):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    if is_directory:
        source.mkdir()
    else:
        source.touch()
    emitter, event_queue = make_emitter(recursive=recursive)
    descriptors = emitter._descriptors  # noqa: SLF001
    source.rename(destination)
    event_type = DirMovedEvent if is_directory else FileMovedEvent
    collect_events(emitter, event_queue, event_type(str(source), str(destination)), DirModifiedEvent(str(tmp_path)))
    assert str(source) not in descriptors
    emitter.queue_events(0)
    mode = destination.stat().st_mode
    attrib_type = DirAttribEvent if is_directory else FileAttribEvent
    try:
        destination.chmod(mode ^ 0o100)
        collect_events(emitter, event_queue, attrib_type(str(destination)))
    finally:
        destination.chmod(mode)


@pytest.mark.parametrize("recursive", [False, True])
def test_recursive_child_events(tmp_path, make_emitter, recursive):
    directory = tmp_path / "directory"
    directory.mkdir()
    existing = directory / "existing"
    existing.write_text("before")
    emitter, event_queue = make_emitter(recursive=recursive)
    with existing.open("a") as stream:
        stream.write("after")
    if recursive:
        events = collect_events(emitter, event_queue, FileModifiedEvent(str(existing)))
    else:
        events = collect_events(emitter, event_queue, timeout=0.2)
    child = directory / "child"
    child.touch()
    if recursive:
        events += collect_events(emitter, event_queue, FileCreatedEvent(str(child)), DirModifiedEvent(str(directory)))
    else:
        events += collect_events(emitter, event_queue, timeout=0.2)
    sentinel = tmp_path / "sentinel"
    sentinel.touch()
    events += collect_events(emitter, event_queue, FileCreatedEvent(str(sentinel)))
    if not recursive:
        # Keep a finite negative window after the sentinel, too.
        events += collect_events(emitter, event_queue, timeout=0.2)
        assert not any(event.src_path in {str(existing), str(child)} for event in events)
        assert DirModifiedEvent(str(directory)) not in events


def test_observer_dispatches_created_event(tmp_path):
    received = Queue()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            received.put(event)

    observer = KqueueObserver(timeout=0.05)
    emitters = []
    try:
        observer.schedule(Handler(), str(tmp_path), recursive=True)
        emitters = list(observer.emitters)
        for emitter in emitters:
            emitter.queue_events(0)
        observer.start()
        path = tmp_path / "created"
        path.touch()
        expected = FileCreatedEvent(str(path))
        deadline = monotonic() + 3
        events = []
        while (remaining := deadline - monotonic()) > 0:
            try:
                events.append(received.get(timeout=remaining))
            except Empty:
                break
            if expected in events:
                break
        assert expected in events, events
    finally:
        observer.stop()
        if observer.ident is not None:
            observer.join(5)
        assert not observer.is_alive()
        assert not observer.emitters
        for emitter in emitters:
            assert not emitter.is_alive()


@pytest.mark.parametrize("err", [errno.EACCES, errno.EPERM])
def test_register_kevent_ignores_permission_errors(tmpdir, err):
    """A file we are not allowed to open must not kill the emitter thread.

    See https://github.com/gorakhargosh/watchdog/issues/1115
    """
    emitter = KqueueEmitter(EventQueue(), ObservedWatch(str(tmpdir), recursive=False), timeout=1)

    # The file appears after the watch was set up, as in the reported scenario.
    path = os.path.join(str(tmpdir), "denied")
    with open(path, "w"):
        pass

    real_open = os.open

    def fake_open(p, flags, *args, **kwargs):
        if p == path:
            raise PermissionError(err, os.strerror(err), p)
        return real_open(p, flags, *args, **kwargs)

    try:
        with patch("os.open", side_effect=fake_open):
            emitter._register_kevent(path, is_directory=False)  # noqa: SLF001
    finally:
        emitter._descriptors.clear()  # noqa: SLF001
