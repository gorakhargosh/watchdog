from __future__ import annotations

import errno
import logging
import os
import stat
import threading
from queue import Empty, Queue
from time import monotonic, sleep

import pytest

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
)
from watchdog.observers.api import ObservedWatch
from watchdog.observers.polling import PollingEmitter as Emitter
from watchdog.utils import platform
from watchdog.utils.dirsnapshot import EmptyDirectorySnapshot

from .shell import chmod, mkdir, msize, mv, rm, touch

SLEEP_TIME = 0.5


@pytest.fixture
def event_queue():
    return Queue()


@pytest.fixture
def emitter(event_queue, p):
    watch = ObservedWatch(str(p()), recursive=True)
    em = Emitter(event_queue, watch, timeout=0.2)
    em.start()
    yield em
    em.stop()
    em.join(5)


@pytest.mark.flaky(max_runs=3, min_passes=1)
def test___init__(p, event_queue, emitter):
    sleep(SLEEP_TIME)
    mkdir(p("project"))

    sleep(SLEEP_TIME)
    mkdir(p("project", "blah"))

    sleep(SLEEP_TIME)
    touch(p("afile"))

    sleep(SLEEP_TIME)
    touch(p("fromfile"))

    sleep(SLEEP_TIME)
    mv(p("fromfile"), p("project", "tofile"))

    sleep(SLEEP_TIME)
    touch(p("afile"))

    sleep(SLEEP_TIME)
    mv(p("project", "blah"), p("project", "boo"))

    sleep(SLEEP_TIME)
    rm(p("project"), recursive=True)

    sleep(SLEEP_TIME)
    rm(p("afile"))

    sleep(SLEEP_TIME)
    msize(p("bfile"))

    sleep(SLEEP_TIME)
    rm(p("bfile"))

    sleep(SLEEP_TIME)
    emitter.stop()

    # What we need here for the tests to pass is a collection type
    # that is:
    #   * unordered
    #   * non-unique
    # A multiset! Python's collections.Counter class seems appropriate.
    expected = {
        DirModifiedEvent(p()),
        DirCreatedEvent(p("project")),
        DirModifiedEvent(p("project")),
        DirCreatedEvent(p("project", "blah")),
        FileCreatedEvent(p("afile")),
        DirModifiedEvent(p()),
        FileCreatedEvent(p("fromfile")),
        DirModifiedEvent(p()),
        DirModifiedEvent(p()),
        FileModifiedEvent(p("afile")),
        DirModifiedEvent(p("project")),
        DirModifiedEvent(p()),
        FileDeletedEvent(p("project", "tofile")),
        DirDeletedEvent(p("project", "boo")),
        DirDeletedEvent(p("project")),
        DirModifiedEvent(p()),
        FileDeletedEvent(p("afile")),
        DirModifiedEvent(p()),
        FileCreatedEvent(p("bfile")),
        FileModifiedEvent(p("bfile")),
        DirModifiedEvent(p()),
        FileDeletedEvent(p("bfile")),
    }

    expected.add(FileMovedEvent(p("fromfile"), p("project", "tofile")))
    expected.add(DirMovedEvent(p("project", "blah"), p("project", "boo")))

    got = set()

    while True:
        try:
            event, _ = event_queue.get_nowait()
            got.add(event)
        except Empty:
            break

    assert expected == got


def _wait_for_failed_polls(emitter, failures, count=2, timeout=5):
    deadline = monotonic() + timeout
    while len(failures) < count and emitter.should_keep_running() and monotonic() < deadline:
        sleep(0.05)


def _wait_for_event(event_queue, expected, timeout=5):
    got = set()
    while expected not in got:
        event, _ = event_queue.get(timeout=timeout)
        got.add(event)
    return got


@pytest.mark.flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("error", ["EACCES", "EBUSY", "EHOSTDOWN", "ESTALE"])
def test_transient_error_on_watched_dir(p, event_queue, caplog, error):
    # A network share that is briefly unreachable must not be reported as
    # deleted, and changes made during the outage must be reported once it
    # is back (#1065).
    code = getattr(errno, error)
    watch = ObservedWatch(p(), recursive=True)
    outage = threading.Event()
    failures = []

    def flaky_stat(path):
        if outage.is_set() and path == watch.path:
            failures.append(path)
            raise OSError(code, os.strerror(code), path)
        return os.stat(path)

    emitter = Emitter(event_queue, watch, timeout=0.2, stat=flaky_stat)
    emitter.start()
    try:
        outage.set()
        touch(p("during_outage"))
        _wait_for_failed_polls(emitter, failures)
        assert emitter.should_keep_running()
        assert len(failures) >= 2
        outage.clear()

        got = _wait_for_event(event_queue, FileCreatedEvent(p("during_outage")))
        assert DirDeletedEvent(p()) not in got
        assert emitter.should_keep_running()
    finally:
        emitter.stop()
        emitter.join(5)

    warnings = [r for r in caplog.records if r.name == "watchdog.observers.polling" and r.levelno == logging.WARNING]
    assert len(warnings) == 1


@pytest.mark.flaky(max_runs=3, min_passes=1)
def test_transient_error_in_subdirectory(p, event_queue):
    mkdir(p("sub"))
    watch = ObservedWatch(p(), recursive=True)
    outage = threading.Event()
    failures = []

    def flaky_listdir(path):
        if outage.is_set() and path == p("sub"):
            failures.append(path)
            raise OSError(errno.EIO, os.strerror(errno.EIO), path)
        return os.scandir(path)

    emitter = Emitter(event_queue, watch, timeout=0.2, listdir=flaky_listdir)
    emitter.start()
    try:
        outage.set()
        touch(p("sub", "during_outage"))
        _wait_for_failed_polls(emitter, failures)
        assert emitter.should_keep_running()
        assert len(failures) >= 2
        outage.clear()

        got = _wait_for_event(event_queue, FileCreatedEvent(p("sub", "during_outage")))
        assert DirDeletedEvent(p()) not in got
        assert emitter.should_keep_running()
    finally:
        emitter.stop()
        emitter.join(5)


@pytest.mark.flaky(max_runs=3, min_passes=1)
def test_delete_watched_dir(p, event_queue, emitter):
    rm(p(), recursive=True)

    sleep(SLEEP_TIME)
    emitter.stop()

    # What we need here for the tests to pass is a collection type
    # that is:
    #   * unordered
    #   * non-unique
    # A multiset! Python's collections.Counter class seems appropriate.
    expected = {
        DirDeletedEvent(p()),
    }

    got = set()

    while True:
        try:
            event, _ = event_queue.get_nowait()
            got.add(event)
        except Empty:
            break

    assert expected == got


def test_polling_emitter_attrib(event_queue, tmp_path):
    # Use tmp_path so this test runs in an isolated directory and is not
    # impacted by test_delete_watched_dir removing the module-level TEMP_DIR.
    temp_dir = str(tmp_path)
    file_path = os.path.join(temp_dir, "attr_file.txt")
    dir_path = os.path.join(temp_dir, "attr_dir")
    touch(file_path)
    mkdir(dir_path)

    watch = ObservedWatch(temp_dir, recursive=True)
    emitter = Emitter(event_queue, watch, timeout=0.1)
    emitter.start()

    # Wait until the emitter thread finishes its initial snapshot before modifying attributes
    while isinstance(emitter._snapshot, EmptyDirectorySnapshot):  # noqa: SLF001
        sleep(0.01)

    mode = stat.S_IREAD if platform.is_windows() else 0o777
    try:
        chmod(file_path, mode)
        chmod(dir_path, mode)

        # Wait for both attribute events with a timeout to prevent flakiness on slow/busy CI runners
        got = set()
        while len(got) < 2:
            event, _ = event_queue.get(timeout=5)
            got.add(event)

        assert FileAttribEvent(file_path) in got
        assert DirAttribEvent(dir_path) in got
        assert FileModifiedEvent(file_path) not in got
        assert DirModifiedEvent(dir_path) not in got
    finally:
        if platform.is_windows():
            chmod(file_path, stat.S_IWRITE)
            chmod(dir_path, stat.S_IWRITE)
        emitter.stop()
        emitter.join(5)
