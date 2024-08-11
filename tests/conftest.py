from __future__ import annotations

import contextlib
import gc
import os
import threading
from functools import partial

import pytest

from .utils import ExpectEvent, Helper, P, StartWatching, TestEventQueue


@pytest.fixture()
def p(tmpdir, *args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return partial(os.path.join, tmpdir)


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
        filename = warning.filename
        if (
            "Not importing directory" in message
            or "Using or importing the ABCs" in message
            or "dns.hash module will be removed in future versions" in message
            or "is still running" in message
            or "eventlet" in filename
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
