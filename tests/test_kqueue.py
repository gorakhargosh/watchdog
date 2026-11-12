from __future__ import annotations

import select

import pytest

# Check for kqueue itself, not the platform name: FreeBSD 15+ reports as
# Linux (it has inotify), but kqueue is still available there.
if not hasattr(select, "kqueue") or not hasattr(select, "KQ_NOTE_DELETE"):
    pytest.skip(
        "kqueue (with KQ_NOTE_* constants) is not supported on this platform/interpreter.", allow_module_level=True
    )

import errno
import os
import queue
import shutil
import threading
import time
from unittest.mock import patch

from watchdog.events import DirDeletedEvent, FileAttribEvent, FileDeletedEvent
from watchdog.observers.api import EventQueue, ObservedWatch
from watchdog.observers.kqueue import KqueueEmitter


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


@pytest.mark.parametrize("remove", ["rename", "rmtree"])
@pytest.mark.parametrize("recursive", [False, True])
def test_watched_dir_removed_stops_emitter(tmpdir, remove, recursive):
    """Removing or moving the watched directory must stop the emitter cleanly
    with a DirDeletedEvent, not kill its thread with FileNotFoundError.

    See https://github.com/gorakhargosh/watchdog/issues/1436
    """
    watched = os.path.join(str(tmpdir), "A")
    os.makedirs(os.path.join(watched, "sub"))
    with open(os.path.join(watched, "sub", "f"), "w"):
        pass

    thread_errors = []
    original_excepthook = threading.excepthook
    threading.excepthook = thread_errors.append

    event_queue = EventQueue()
    emitter = KqueueEmitter(event_queue, ObservedWatch(watched, recursive=recursive), timeout=0.1)
    try:
        emitter.start()
        time.sleep(0.2)
        if remove == "rename":
            os.rename(watched, watched + ".1")
        else:
            shutil.rmtree(watched)
        emitter.join(5)
        assert not emitter.is_alive()
    finally:
        emitter.stop()
        threading.excepthook = original_excepthook

    assert thread_errors == []

    events = []
    while not event_queue.empty():
        event, _ = event_queue.get_nowait()
        events.append(event)
    deleted = [e for e in events if e == DirDeletedEvent(watched)]
    assert len(deleted) == 1
    assert events[-1] == DirDeletedEvent(watched)


@pytest.mark.parametrize("change", ["delete", "chmod"])
def test_changes_before_start_are_reported(tmpdir, change):
    """Changes made between creating the emitter and its thread's first
    kqueue.control() call must still be reported.

    Deletes and attribute changes come from kevents only. If the kevents are
    handed to the kernel only in the emitter thread, these changes are lost
    (always with free-threaded Python, which runs both threads at once).
    """
    path = os.path.join(str(tmpdir), "a")
    with open(path, "w"):
        pass
    os.chmod(path, 0o644)

    event_queue = EventQueue()
    emitter = KqueueEmitter(event_queue, ObservedWatch(str(tmpdir), recursive=False), timeout=0.1)
    if change == "delete":
        os.remove(path)
        expected = FileDeletedEvent(path)
    else:
        os.chmod(path, 0o600)
        expected = FileAttribEvent(path)

    emitter.start()
    try:
        events = []
        deadline = time.monotonic() + 5
        while expected not in events and time.monotonic() < deadline:
            try:
                event, _ = event_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            events.append(event)
    finally:
        emitter.stop()
        emitter.join(5)

    assert expected in events
