from __future__ import annotations

import time
from pathlib import Path

import pytest

from watchdog.events import FileModifiedEvent, FileOpenedEvent, LoggingEventHandler
from watchdog.observers.api import BaseObserver, EventDispatcher, EventEmitter, EventQueue, ObservedWatch


def test_observer_constructor():
    ObservedWatch(Path("/foobar"), recursive=True)


def test_observer__eq__():
    watch1 = ObservedWatch("/foobar", recursive=True)
    watch2 = ObservedWatch("/foobar", recursive=True)
    watch_ne1 = ObservedWatch("/foo", recursive=True)
    watch_ne2 = ObservedWatch("/foobar", recursive=False)

    assert watch1 == watch2
    assert watch1.__eq__(watch2)
    assert not watch1.__eq__(watch_ne1)
    assert not watch1.__eq__(watch_ne2)


def test_observer__ne__():
    watch1 = ObservedWatch("/foobar", recursive=True)
    watch2 = ObservedWatch("/foobar", recursive=True)
    watch_ne1 = ObservedWatch("/foo", recursive=True)
    watch_ne2 = ObservedWatch("/foobar", recursive=False)

    assert not watch1.__ne__(watch2)
    assert watch1.__ne__(watch_ne1)
    assert watch1.__ne__(watch_ne2)


def test_observer__repr__():
    observed_watch = ObservedWatch("/foobar", recursive=True)
    repr_str = "<ObservedWatch: path='/foobar', is_recursive=True>"
    assert observed_watch.__repr__() == repr(observed_watch)
    assert repr(observed_watch) == repr_str

    observed_watch = ObservedWatch("/foobar", recursive=False, event_filter=[FileOpenedEvent, FileModifiedEvent])
    repr_str = "<ObservedWatch: path='/foobar', is_recursive=False, event_filter=FileModifiedEvent|FileOpenedEvent>"
    assert observed_watch.__repr__() == repr(observed_watch)
    assert repr(observed_watch) == repr_str


def test_event_emitter():
    event_queue = EventQueue()
    watch = ObservedWatch("/foobar", recursive=True)
    event_emitter = EventEmitter(event_queue, watch, timeout=1)
    event_emitter.queue_event(FileModifiedEvent("/foobar/blah"))


def test_event_dispatcher():
    event = FileModifiedEvent("/foobar")
    watch = ObservedWatch("/path", recursive=True)

    class TestableEventDispatcher(EventDispatcher):
        def dispatch_event(self, event, watch):
            assert True

    event_dispatcher = TestableEventDispatcher()
    event_dispatcher.event_queue.put((event, watch))
    event_dispatcher.start()
    time.sleep(1)
    event_dispatcher.stop()
    event_dispatcher.join()


def test_observer_basic():
    observer = BaseObserver(EventEmitter)
    handler = LoggingEventHandler()

    watch = observer.schedule(handler, "/foobar", recursive=True)
    observer.add_handler_for_watch(handler, watch)
    observer.add_handler_for_watch(handler, watch)
    observer.remove_handler_for_watch(handler, watch)
    with pytest.raises(KeyError):
        observer.remove_handler_for_watch(handler, watch)
    observer.unschedule(watch)
    with pytest.raises(KeyError):
        observer.unschedule(watch)

    watch = observer.schedule(handler, "/foobar", recursive=True)
    observer.event_queue.put((FileModifiedEvent("/foobar"), watch))
    observer.start()
    time.sleep(1)
    observer.unschedule_all()
    observer.stop()
    observer.join()


def test_observer_marks_every_queued_item_done():
    """The observer must mark both the dispatched event and the stop sentinel done.

    ``BaseObserver.dispatch_events()`` calls ``event_queue.task_done()`` on the
    stop-sentinel path as well as after dispatching. Without the sentinel call a
    caller's ``event_queue.join()`` never returns, and nothing else here notices:
    the other tests only join the *thread*, which stops either way.
    """
    observer = BaseObserver(EventEmitter)
    handler = LoggingEventHandler()

    watch = observer.schedule(handler, "/foobar", recursive=True)
    observer.event_queue.put((FileModifiedEvent("/foobar"), watch))
    observer.start()
    time.sleep(1)
    observer.unschedule_all()
    observer.stop()
    observer.join()

    # Asserted rather than calling event_queue.join(), which would hang the run
    # instead of failing if either task_done() goes missing.
    assert observer.event_queue.unfinished_tasks == 0
