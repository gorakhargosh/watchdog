from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers.api import BaseObserver, EventEmitter

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture()
def observer() -> Iterator[BaseObserver]:
    obs = BaseObserver(EventEmitter)
    yield obs
    obs.stop()
    with contextlib.suppress(RuntimeError):
        obs.join()


@pytest.fixture()
def observer2():
    obs = BaseObserver(EventEmitter)
    yield obs
    obs.stop()
    with contextlib.suppress(RuntimeError):
        obs.join()


def test_schedule_should_start_emitter_if_running(observer):
    observer.start()
    observer.schedule(None, "")
    (emitter,) = observer.emitters
    assert emitter.is_alive()


def test_schedule_should_not_start_emitter_if_not_running(observer):
    observer.schedule(None, "")
    (emitter,) = observer.emitters
    assert not emitter.is_alive()


def test_start_should_start_emitter(observer):
    observer.schedule(None, "")
    observer.start()
    (emitter,) = observer.emitters
    assert emitter.is_alive()


def test_stop_should_stop_emitter(observer):
    observer.schedule(None, "")
    observer.start()
    (emitter,) = observer.emitters
    assert emitter.is_alive()
    observer.stop()
    observer.join()
    assert not observer.is_alive()
    assert not emitter.is_alive()


def test_unschedule_self(observer):
    """
    Tests that unscheduling a watch from within an event handler correctly
    correctly unregisters emitter and handler without deadlocking.
    """

    class EventHandler(FileSystemEventHandler):
        def on_modified(self, event):
            observer.unschedule(watch)
            unschedule_finished.set()

    unschedule_finished = threading.Event()
    watch = observer.schedule(EventHandler(), "")
    observer.start()

    (emitter,) = observer.emitters
    emitter.queue_event(FileModifiedEvent(""))

    assert unschedule_finished.wait()
    assert len(observer.emitters) == 0


def test_schedule_after_unschedule_all(observer):
    observer.start()
    observer.schedule(None, "")
    assert len(observer.emitters) == 1

    observer.unschedule_all()
    assert len(observer.emitters) == 0

    observer.schedule(None, "")
    assert len(observer.emitters) == 1


def test_2_observers_on_the_same_path(observer, observer2):
    assert observer is not observer2

    observer.schedule(None, "")
    assert len(observer.emitters) == 1

    observer2.schedule(None, "")
    assert len(observer2.emitters) == 1


def test_start_failure_should_not_prevent_further_try(observer):
    observer.schedule(None, "")
    emitters = observer.emitters
    assert len(emitters) == 1

    # Make the emitter to fail on start()

    def mocked_start():
        raise OSError("Mock'ed!")

    emitter = next(iter(emitters))
    with patch.object(emitter, "start", new=mocked_start), pytest.raises(OSError, match="Mock'ed!"):
        observer.start()
    # The emitter should be removed from the list
    assert len(observer.emitters) == 0

    # Restoring the original behavior should work like there never be emitters
    observer.start()
    assert len(observer.emitters) == 0

    # Re-scheduling the watch should work
    observer.schedule(None, "")
    assert len(observer.emitters) == 1


def test_schedule_failure_should_not_prevent_future_schedules(observer):
    observer.start()

    # Make the emitter fail on start(), and subsequently the observer to fail on schedule()
    def bad_start(_):
        raise OSError("Mock'ed!")

    with patch.object(EventEmitter, "start", new=bad_start), pytest.raises(OSError, match="Mock'ed!"):
        observer.schedule(None, "")
    # The emitter should not be in the list
    assert not observer.emitters

    # Re-scheduling the watch should work
    observer.schedule(None, "")
    assert len(observer.emitters) == 1
