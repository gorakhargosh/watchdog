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


@pytest.fixture
def sysfs_file(tmp_path, monkeypatch):
    if not platform.is_linux():
        pytest.skip("sysfs polling is Linux-specific")
    directory = tmp_path / "sysfs"
    directory.mkdir()
    path = directory / "rx_bytes"
    path.write_bytes(b"100\n")

    # Model sysfs without requiring it on the test machine. Resolve symlinks
    # normally, then map this temporary directory into /sys.
    realpath = os.path.realpath

    def sysfs_realpath(path, **kwargs):
        resolved = realpath(path, **kwargs)
        if resolved == str(directory):
            return "/sys/devices/watchdog-test"
        prefix = str(directory) + os.sep
        if resolved.startswith(prefix):
            return "/sys/devices/watchdog-test/" + resolved[len(prefix) :]
        return resolved

    monkeypatch.setattr(os.path, "realpath", sysfs_realpath)
    return path


def change_sysfs_file(path):
    before = path.stat()
    path.write_bytes(b"200\n")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = path.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )


@pytest.mark.parametrize("use_bytes", [False, True])
@pytest.mark.parametrize("use_symlink", [False, True])
def test_sysfs_content_change(sysfs_file, tmp_path, event_queue, use_bytes, use_symlink):
    watched = sysfs_file.parent
    if use_symlink:
        watched = tmp_path / "link"
        watched.symlink_to(sysfs_file.parent, target_is_directory=True)
    path = os.fsencode(watched) if use_bytes else str(watched)
    expected_path = os.path.join(path, b"rx_bytes" if use_bytes else "rx_bytes")
    watch = ObservedWatch(path, recursive=True)
    emitter = Emitter(event_queue, watch)
    emitter.on_thread_start()
    emitter.queue_events(0)
    assert event_queue.empty()

    change_sysfs_file(sysfs_file)
    emitter.queue_events(0)
    assert event_queue.get_nowait() == (FileModifiedEvent(expected_path), watch)
    assert event_queue.empty()

    emitter.queue_events(0)
    assert event_queue.empty()


@pytest.mark.parametrize("error", [errno.EACCES, errno.EIO, errno.ENOENT])
def test_sysfs_read_error(sysfs_file, event_queue, monkeypatch, error):
    watch = ObservedWatch(str(sysfs_file.parent), recursive=True)
    emitter = Emitter(event_queue, watch)
    emitter.on_thread_start()

    def unreadable(*args, **kwargs):
        raise OSError(error, os.strerror(error))

    with monkeypatch.context() as patch:
        patch.setattr("watchdog.observers.polling.open", unreadable, raising=False)
        change_sysfs_file(sysfs_file)
        emitter.queue_events(0)
        assert event_queue.empty()
        assert emitter.should_keep_running()

    # A temporary read failure must not discard the last readable value.
    emitter.queue_events(0)
    assert event_queue.get_nowait() == (FileModifiedEvent(str(sysfs_file)), watch)
    assert event_queue.empty()


def test_sysfs_metadata_and_content_change(sysfs_file, event_queue):
    watch = ObservedWatch(str(sysfs_file.parent), recursive=True)
    emitter = Emitter(event_queue, watch)
    emitter.on_thread_start()
    sysfs_file.write_bytes(b"20000\n")
    emitter.queue_events(0)
    assert event_queue.get_nowait() == (FileModifiedEvent(str(sysfs_file)), watch)
    assert event_queue.empty()


@pytest.mark.parametrize("custom_fs", [None, "stat", "listdir"])
def test_polling_does_not_read_other_files(sysfs_file, tmp_path, event_queue, monkeypatch, custom_fs):
    path = sysfs_file
    kwargs = {}
    if custom_fs == "stat":
        kwargs["stat"] = lambda path: os.stat(path)
    elif custom_fs == "listdir":
        kwargs["listdir"] = lambda path: os.scandir(path)
    else:
        directory = tmp_path / "ordinary"
        directory.mkdir()
        path = directory / "rx_bytes"
        path.write_bytes(b"100\n")
    watch = ObservedWatch(str(path.parent), recursive=True)

    def unexpected_read(*args, **kwargs):
        pytest.fail("Polling must not read ordinary files or custom filesystems")

    monkeypatch.setattr("watchdog.observers.polling.open", unexpected_read, raising=False)
    emitter = Emitter(event_queue, watch, **kwargs)
    emitter.on_thread_start()
    path.write_bytes(b"20000\n")
    emitter.queue_events(0)
    assert event_queue.get_nowait() == (FileModifiedEvent(str(path)), watch)
    assert event_queue.empty()


def test_sysfs_initial_read_error(sysfs_file, event_queue, monkeypatch):
    watch = ObservedWatch(str(sysfs_file.parent), recursive=True)
    emitter = Emitter(event_queue, watch)

    def unreadable(*args, **kwargs):
        raise PermissionError

    with monkeypatch.context() as patch:
        patch.setattr("watchdog.observers.polling.open", unreadable, raising=False)
        emitter.on_thread_start()
        emitter.queue_events(0)
        assert event_queue.empty()

    emitter.queue_events(0)
    assert event_queue.empty()
    change_sysfs_file(sysfs_file)
    emitter.queue_events(0)
    assert event_queue.get_nowait() == (FileModifiedEvent(str(sysfs_file)), watch)
    assert event_queue.empty()


def test_sysfs_replaced_file(sysfs_file, tmp_path, event_queue):
    watch = ObservedWatch(str(sysfs_file.parent), recursive=True)
    emitter = Emitter(event_queue, watch, event_filter=[FileCreatedEvent, FileDeletedEvent, FileModifiedEvent])
    emitter.on_thread_start()
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"200\n")
    assert replacement.stat().st_ino != sysfs_file.stat().st_ino
    replacement.replace(sysfs_file)
    emitter.queue_events(0)
    assert {event_queue.get_nowait()[0], event_queue.get_nowait()[0]} == {
        FileCreatedEvent(str(sysfs_file)),
        FileDeletedEvent(str(sysfs_file)),
    }
    assert event_queue.empty()


def test_sysfs_does_not_read_special_files(sysfs_file, event_queue, monkeypatch):
    sysfs_file.unlink()
    os.mkfifo(sysfs_file)

    def unexpected_read(*args, **kwargs):
        pytest.fail("Polling must not open special files or directories")

    monkeypatch.setattr("watchdog.observers.polling.open", unexpected_read, raising=False)
    watch = ObservedWatch(str(sysfs_file.parent), recursive=True)
    emitter = Emitter(event_queue, watch)
    emitter.on_thread_start()
    emitter.queue_events(0)
    assert event_queue.empty()


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
