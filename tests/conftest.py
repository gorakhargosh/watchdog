from __future__ import annotations

import contextlib
import gc
import os
import threading
import time
from functools import partial

import pytest

from watchdog.utils import platform

from .utils import EventsChecker, ExpectEvent, Helper, P, StartWatching, TestEventQueue


@pytest.fixture
def p(tmpdir, *args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return partial(os.path.join, tmpdir)


@pytest.fixture(scope="session", autouse=True)
def _inotify_instance():
    """Manage the shared inotify reader outside per-test thread leak checks."""
    if not platform.is_linux():
        yield
        return

    from watchdog.observers.inotify_c import InotifyFD

    inotify_fd = InotifyFD.get_instance()
    # InotifyFD (InotifyFD-Reader) spawns a secondary background thread (InotifyFD-Dispatcher)
    # in its run() loop. Under PyPy JIT warm-up or free-threaded Python (PEP 703 / nogil),
    # get_instance() may return before the dispatcher thread is registered by the OS scheduler.
    # We poll until InotifyFD-Dispatcher is active so that function-scoped _no_thread_leaks
    # fixtures capture both inotify threads in their baseline thread count, preventing false
    # thread-leak assertions (e.g. 'assert 3 == 2' in CI).
    deadline = time.monotonic() + 5.0
    while not any(thread.name == "InotifyFD-Dispatcher" for thread in threading.enumerate()):
        if time.monotonic() >= deadline:
            raise AssertionError("InotifyFD dispatcher thread did not start within 5.0s")
        time.sleep(0.001)

    assert inotify_fd.is_alive()

    try:
        yield
    finally:
        inotify_fd.stop()
        inotify_fd.join(5)
        assert not inotify_fd.is_alive()


@pytest.fixture(autouse=True)
def _no_thread_leaks():
    """
    Fail on thread leak.
    We do not use pytest-threadleak because it is not reliable.
    """
    old_thread_count = threading.active_count()
    yield
    gc.collect()  # Clear the stuff from other function-level fixtures
    assert threading.active_count() == old_thread_count  # Only previously existing threads


@pytest.fixture(autouse=True)
def _no_warnings(recwarn):
    """Fail on warning."""

    yield

    warnings = []
    for warning in recwarn:  # pragma: no cover
        message = str(warning.message)
        if (
            "Not importing directory" in message
            or "Using or importing the ABCs" in message
            or "dns.hash module will be removed in future versions" in message
            or "is still running" in message
        ):
            continue
        warnings.append(f"{warning.filename}:{warning.lineno} {warning.message}")
    assert not warnings, warnings


@pytest.fixture(name="helper")
def helper_fixture(tmpdir):
    with contextlib.closing(Helper(tmp=os.fspath(tmpdir))) as helper:
        yield helper


@pytest.fixture(name="p")
def p_fixture(helper: Helper) -> P:
    return helper.joinpath


@pytest.fixture(name="event_queue")
def event_queue_fixture(helper: Helper) -> TestEventQueue:
    return helper.event_queue


@pytest.fixture(name="start_watching")
def start_watching_fixture(helper: Helper) -> StartWatching:
    return helper.start_watching


@pytest.fixture(name="expect_event")
def expect_event_fixture(helper: Helper) -> ExpectEvent:
    return helper.expect_event


@pytest.fixture(name="events_checker")
def events_checker_fixture(helper: Helper) -> EventsChecker:
    return helper.events_checker
