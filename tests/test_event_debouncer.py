from __future__ import annotations

import threading
import warnings
from queue import Queue
from types import SimpleNamespace

import pytest

from watchdog.events import FileModifiedEvent
from watchdog.utils import event_debouncer
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


class ObservedCondition(threading.Condition):
    """Expose wait boundaries without sleeping to guess the worker's state."""

    def __init__(self):
        super().__init__()
        self.waits = Queue()

    def wait(self, timeout=None):
        self.waits.put(timeout)
        return super().wait(timeout)

    def expect_wait(self, timeout):
        assert self.waits.get(timeout=5) == timeout
        # wait() publishes before releasing its lock. Acquiring it here ensures
        # the worker has actually entered the wait before the test continues.
        with self:
            pass


def test_event_debouncer_coalesce_and_drain(monkeypatch):
    called = []
    delivered = threading.Event()
    e1 = FileModifiedEvent("/some/path1")
    e2 = FileModifiedEvent("/some/path2")
    e3 = FileModifiedEvent("/some/path3")

    def callback(events):
        called.append(events)
        delivered.set()

    debouncer = EventDebouncer(0.01, callback)
    cond = ObservedCondition()
    monkeypatch.setattr(debouncer, "_cond", cond)
    debouncer.start()
    try:
        cond.expect_wait(None)
        with cond:
            assert not called
            # Both events arrive before the worker can inspect the batch.
            debouncer.handle_event(e1)
            debouncer.handle_event(e2)
        assert delivered.wait(5)
        cond.expect_wait(0.01)
        cond.expect_wait(None)
        assert called == [[e1, e2]]

        with cond:
            # Stop before the worker can process this event normally. It must
            # drain the pending event, without delivering the old batch twice.
            debouncer.handle_event(e3)
            debouncer.stop()
    finally:
        debouncer.stop()
        debouncer.join(5)
    assert not debouncer.is_alive()
    assert called == [[e1, e2], [e3]]


def test_event_debouncer_starvation(monkeypatch):
    called = []
    now = 0.0
    monkeypatch.setattr(event_debouncer, "time", SimpleNamespace(monotonic=lambda: now))
    debouncer = EventDebouncer(60, called.append)
    cond = ObservedCondition()
    monkeypatch.setattr(debouncer, "_cond", cond)
    batches = [[FileModifiedEvent(f"/batch{batch}/path{i}") for i in range(4)] for batch in range(2)]
    debouncer.start()
    try:
        cond.expect_wait(None)
        for batch, events in enumerate(batches):
            with cond:
                now = batch * 100.0
                debouncer.handle_event(events[0])
            cond.expect_wait(60)
            for event, elapsed in zip(events[1:], [20.0, 40.0, 61.0], strict=True):
                with cond:
                    now = batch * 100.0 + elapsed
                    debouncer.handle_event(event)
                if elapsed < 60:
                    cond.expect_wait(60)
                    with cond:
                        assert called == batches[:batch]
            # Notifications did not let the worker time out. The elapsed-time
            # limit must still flush the batch, preventing starvation. Repeat
            # for another batch to verify the elapsed timer starts afresh.
            cond.expect_wait(None)
            assert called == batches[: batch + 1]
    finally:
        debouncer.stop()
        debouncer.join(5)
    assert not debouncer.is_alive()


def test_event_debouncer_stop_while_idle(monkeypatch):
    called = []
    debouncer = EventDebouncer(60, called.append)
    cond = ObservedCondition()
    monkeypatch.setattr(debouncer, "_cond", cond)
    debouncer.start()
    try:
        cond.expect_wait(None)
    finally:
        debouncer.stop()
        debouncer.join(5)
    assert not debouncer.is_alive()
    assert called == []


def test_event_debouncer_stop_during_debounce(monkeypatch):
    called = []
    event = FileModifiedEvent("/some/path")
    debouncer = EventDebouncer(60, called.append)
    cond = ObservedCondition()
    monkeypatch.setattr(debouncer, "_cond", cond)
    debouncer.start()
    try:
        cond.expect_wait(None)
        debouncer.handle_event(event)
        cond.expect_wait(60)
    finally:
        debouncer.stop()
        debouncer.join(5)
    assert not debouncer.is_alive()
    assert called == [[event]]


def test_event_debouncer_zero_interval(monkeypatch):
    called = []
    event = FileModifiedEvent("/some/path")
    debouncer = EventDebouncer(0, called.append)
    cond = ObservedCondition()
    monkeypatch.setattr(debouncer, "_cond", cond)
    debouncer.start()
    try:
        cond.expect_wait(None)
        debouncer.handle_event(event)
        # A zero interval must go straight back to waiting for another event,
        # without a timed debounce wait or an empty callback.
        cond.expect_wait(None)
        assert called == [[event]]
    finally:
        debouncer.stop()
        debouncer.join(5)
    assert not debouncer.is_alive()
