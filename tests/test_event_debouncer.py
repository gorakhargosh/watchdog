from __future__ import annotations

import time
import warnings

import pytest

from watchdog.events import FileModifiedEvent
from watchdog.utils.event_debouncer import EventDebouncer


def _callback(events):
    pass


def test_debounce_interval_positional():
    debouncer = EventDebouncer(0.5, _callback)
    assert debouncer.debounce_interval == 0.5
    assert debouncer.events_callback is _callback


def test_debounce_interval_keyword():
    debouncer = EventDebouncer(debounce_interval=0.5, events_callback=_callback)
    assert debouncer.debounce_interval == 0.5


def test_deprecated_debounce_interval_seconds_argument():
    with pytest.warns(DeprecationWarning, match="'debounce_interval_seconds' is deprecated") as record:
        debouncer = EventDebouncer(debounce_interval_seconds=0.5, events_callback=_callback)
    assert debouncer.debounce_interval == 0.5
    assert len(record) == 1
    # The warning points at the caller, not at watchdog.
    assert record[0].filename == __file__


def test_debounce_interval_and_deprecated_name_conflict():
    with pytest.raises(TypeError, match="Cannot pass both"):
        EventDebouncer(0.5, events_callback=_callback, debounce_interval_seconds=0.5)


def test_missing_arguments():
    with pytest.raises(TypeError, match="'debounce_interval'"):
        EventDebouncer(events_callback=_callback)
    with pytest.raises(TypeError, match="'events_callback'"):
        EventDebouncer(0.5)


def test_deprecated_debounce_interval_seconds_attribute():
    debouncer = EventDebouncer(0.5, _callback)

    with pytest.warns(DeprecationWarning, match="'debounce_interval_seconds' is deprecated") as record:
        assert debouncer.debounce_interval_seconds == 0.5
    assert record[0].filename == __file__

    with pytest.warns(DeprecationWarning, match="'debounce_interval_seconds' is deprecated"):
        debouncer.debounce_interval_seconds = 2
    assert debouncer.debounce_interval == 2


def test_no_warning_with_new_names():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        debouncer = EventDebouncer(0.5, _callback)
        assert debouncer.debounce_interval == 0.5


def test_event_debouncer_coalesce_and_drain():
    called = []
    e1 = FileModifiedEvent("/some/path1")
    e2 = FileModifiedEvent("/some/path2")
    debouncer = EventDebouncer(0.05, called.append)
    debouncer.start()
    try:
        # Does not emit when idle
        time.sleep(0.06)
        assert not called

        # Coalesces burst of events into a single callback
        debouncer.handle_event(e1)
        debouncer.handle_event(e2)

        deadline = time.monotonic() + 2.0
        while not called and time.monotonic() < deadline:
            time.sleep(0.01)
        assert called == [[e1, e2]]

        # Drains pending events upon stop()
        e3 = FileModifiedEvent("/some/path3")
        debouncer.handle_event(e3)
    finally:
        debouncer.stop()
        debouncer.join()

    assert called == [[e1, e2], [e3]]


def test_event_debouncer_starvation():
    called = []
    debouncer = EventDebouncer(0.03, called.append)
    debouncer.start()
    try:
        for i in range(8):
            debouncer.handle_event(FileModifiedEvent(f"/some/path{i}"))
            time.sleep(0.01)

        deadline = time.monotonic() + 2.0
        while not called and time.monotonic() < deadline:
            time.sleep(0.01)

        # Flushes periodically despite rapid continuous events (fixes #997)
        assert len(called) >= 1
    finally:
        debouncer.stop()
        debouncer.join()
