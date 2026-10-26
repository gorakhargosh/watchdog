from __future__ import annotations

import warnings

import pytest

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
