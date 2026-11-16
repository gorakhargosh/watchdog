from __future__ import annotations

import threading
import time
from pathlib import Path
from threading import Event

import pytest

from watchdog.events import (
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
    FileSystemEventHandler,
    LoggingEventHandler,
)
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


def test_observer__eq__ignores_follow_symlink():
    """Two watches that differ only in ``follow_symlink`` must not compare equal.

    ``ObservedWatch.key`` used to build its tuple from ``path``, ``is_recursive`` and
    ``event_filter`` only, omitting ``follow_symlink`` even though the latter is a
    real constructor parameter stored on the instance. ``event_filter`` was
    deliberately added to the key so that two watches on the same path with
    different filters stay independent; ``follow_symlink`` should get the same
    treatment, otherwise scheduling the same path twice with different
    ``follow_symlink`` values collapses onto a single watch (see
    ``test_observer_schedule_respects_second_follow_symlink`` below for the
    resulting observer-level bug).
    """
    watch_no_follow = ObservedWatch("/foobar", recursive=True, follow_symlink=False)
    watch_follow = ObservedWatch("/foobar", recursive=True, follow_symlink=True)

    assert watch_no_follow != watch_follow
    assert hash(watch_no_follow) != hash(watch_follow)


def test_observer_schedule_respects_second_follow_symlink():
    """A second ``schedule()`` call for the same path must honor its own follow_symlink.

    Because ``ObservedWatch`` equality used to ignore ``follow_symlink``, scheduling
    "/foobar" with ``follow_symlink=False`` and then again with
    ``follow_symlink=True`` makes the second watch compare equal to the first.
    ``BaseObserver.schedule()`` then treats an emitter as already existing for it
    and never creates one for the ``follow_symlink=True`` request: the emitter
    actually reachable from the returned watch still reports
    ``follow_symlink=False``, silently dropping the caller's request.
    """
    observer = BaseObserver(EventEmitter)
    handler = LoggingEventHandler()

    watch_no_follow = observer.schedule(handler, "/foobar", recursive=True, follow_symlink=False)
    watch_follow = observer.schedule(handler, "/foobar", recursive=True, follow_symlink=True)

    assert len(observer.emitters) == 2
    assert not observer._emitter_for_watch[watch_no_follow].watch.follow_symlink  # noqa: SLF001
    assert observer._emitter_for_watch[watch_follow].watch.follow_symlink  # noqa: SLF001


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


def test_stale_event_does_not_resurrect_an_unscheduled_watch():
    """A watch removed by unschedule() must stay removed when a queued event lands.

    ``BaseObserver._handlers`` is a ``defaultdict(set)``, so indexing it in
    ``dispatch_events()`` recreates whatever key it is given. An event queued
    before ``unschedule()`` is still dispatched afterwards, which put the removed
    watch back as an empty set that nothing ever cleans up.
    """
    observer = BaseObserver(EventEmitter)
    handler = LoggingEventHandler()

    watch = observer.schedule(handler, "/foobar", recursive=True)
    observer.event_queue.put((FileModifiedEvent("/foobar"), watch))
    observer.unschedule(watch)
    assert watch not in observer._handlers  # noqa: SLF001

    observer.dispatch_events(observer.event_queue)

    assert watch not in observer._handlers  # noqa: SLF001


def test_event_dispatcher_timeout_rejects_bool():
    """bool subclasses int; timeout=True must not silently become 1.0s."""
    with pytest.raises(TypeError, match=r"timeout.*bool"):
        EventDispatcher(timeout=True)
    with pytest.raises(TypeError, match=r"timeout.*bool"):
        EventDispatcher(timeout=False)


def test_base_observer_timeout_rejects_bool():
    """BaseObserver forwards timeout to EventDispatcher."""
    with pytest.raises(TypeError, match=r"timeout.*bool"):
        BaseObserver(EventEmitter, timeout=True)
    with pytest.raises(TypeError, match=r"timeout.*bool"):
        BaseObserver(EventEmitter, timeout=False)


def test_event_emitter_timeout_rejects_bool():
    watch = ObservedWatch("/foobar", recursive=False)
    with pytest.raises(TypeError, match=r"timeout.*bool"):
        EventEmitter(EventQueue(), watch, timeout=True)
    with pytest.raises(TypeError, match=r"timeout.*bool"):
        EventEmitter(EventQueue(), watch, timeout=False)


def test_remove_handler_for_watch_does_not_resurrect_unscheduled_watch():
    """remove_handler_for_watch() must not resurrect a watch removed by unschedule().

    ``BaseObserver._handlers`` is a ``defaultdict(set)``, so indexing it in
    ``remove_handler_for_watch()`` recreates whatever key it is given. Calling it
    for a watch that ``unschedule()`` already removed re-creates that watch as an
    empty set that nothing will ever clean up, the same leak ``dispatch_events()``
    had before it switched to ``.get()``.
    """
    observer = BaseObserver(EventEmitter)
    handler = LoggingEventHandler()

    watch = observer.schedule(handler, "/foobar", recursive=True)
    observer.unschedule(watch)
    assert watch not in observer._handlers  # noqa: SLF001

    with pytest.raises(KeyError):
        observer.remove_handler_for_watch(handler, watch)

    assert watch not in observer._handlers  # noqa: SLF001


def test_observed_watch_single_file(tmp_path: Path):
    """When an ObservedWatch is created on a single file, its watch path is set to the parent directory."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")

    watch = ObservedWatch(file_path, recursive=True)
    assert watch.is_file
    assert watch.raw_path == str(file_path)
    assert watch.path == str(tmp_path.resolve())
    assert not watch.is_recursive


def test_single_file_symlink_follow(tmp_path: Path):
    """When follow_symlink=True, a symlink to a file watches the target's parent directory."""
    target_dir = tmp_path / "target_dir"
    target_dir.mkdir()
    target_file = target_dir / "target.txt"
    target_file.write_text("hello")

    link_dir = tmp_path / "link_dir"
    link_dir.mkdir()
    symlink_file = link_dir / "link.txt"
    symlink_file.symlink_to(target_file)

    watch = ObservedWatch(symlink_file, recursive=False, follow_symlink=True)
    assert watch.is_file
    assert watch.path == str(target_dir.resolve())


def test_single_file_symlink_no_follow(tmp_path: Path):
    """When follow_symlink=False, a symlink to a file watches the symlink's own parent directory."""
    target_dir = tmp_path / "target_dir"
    target_dir.mkdir()
    target_file = target_dir / "target.txt"
    target_file.write_text("hello")

    link_dir = tmp_path / "link_dir"
    link_dir.mkdir()
    symlink_file = link_dir / "link.txt"
    symlink_file.symlink_to(target_file)

    watch = ObservedWatch(symlink_file, recursive=False, follow_symlink=False)
    assert watch.is_file
    assert watch.path == str(link_dir.resolve())


def test_single_file_dispatch_events(tmp_path: Path):
    """Dispatches events for watched single file and moves, filtering out unrelated events."""
    file_a = tmp_path / "a.txt"
    file_a.write_text("a")
    file_b = tmp_path / "b.txt"
    other = tmp_path / "other.txt"
    other.write_text("o")

    events = []

    class Handler(LoggingEventHandler):
        def dispatch(self, event):
            events.append(event)

    observer = BaseObserver(EventEmitter)
    watch_a = observer.schedule(Handler(), file_a)

    # Watched file modified -> dispatched
    mod_event = FileModifiedEvent(str(file_a))
    observer.event_queue.put((mod_event, watch_a))
    # Unrelated file modified -> filtered out
    observer.event_queue.put((FileModifiedEvent(str(other)), watch_a))
    # Watched file moved -> dispatched
    move_event = FileMovedEvent(str(file_a), str(file_b))
    observer.event_queue.put((move_event, watch_a))

    observer.dispatch_events(observer.event_queue)
    observer.dispatch_events(observer.event_queue)
    observer.dispatch_events(observer.event_queue)

    assert events == [mod_event, move_event]


def test_symlinked_directory_not_treated_as_file(tmp_path: Path):
    """A symlink pointing to a directory must not be treated as a single file watch."""
    target_dir = tmp_path / "target_dir"
    target_dir.mkdir()
    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(target_dir, target_is_directory=True)

    watch = ObservedWatch(link_dir, recursive=True, follow_symlink=False)
    assert not watch.is_file
    assert watch.is_recursive
    assert watch.path == str(link_dir)

    watch_follow = ObservedWatch(link_dir, recursive=True, follow_symlink=True)
    assert not watch_follow.is_file
    assert watch_follow.is_recursive


def test_schedule_defers_emitter_start() -> None:
    """Scheduling a watch must be non-blocking and not invoke emitter initialization before observer.start().

    See https://github.com/gorakhargosh/watchdog/issues/96
    """
    started = Event()

    class CustomEmitter(EventEmitter):
        def on_thread_start(self) -> None:
            started.set()

    observer = BaseObserver(CustomEmitter)
    watch = observer.schedule(FileSystemEventHandler(), "/path/to/watch", recursive=True)

    assert not started.is_set(), "Emitter must not execute on_thread_start during schedule()"
    assert not observer.is_alive(), "Observer thread must not be running before start()"
    assert len(observer.emitters) == 1
    assert next(iter(observer.emitters)).watch == watch

    observer.start()
    try:
        assert started.wait(timeout=2.0), "Emitter on_thread_start must be called upon observer.start()"
    finally:
        observer.stop()
        observer.join()


def test_lock_not_held_during_handler_dispatch() -> None:
    """User handler execution must not hold observer lock to avoid blocking schedule/unschedule."""

    class FastEmitter(EventEmitter):
        def queue_events(self, timeout: float) -> None:
            self.stopped_event.wait(timeout=timeout)

    observer = BaseObserver(FastEmitter, timeout=0.01)
    handler_entered = Event()
    release_handler = Event()
    schedule_succeeded = Event()

    class BlockingHandler(FileSystemEventHandler):
        def on_modified(self, event):
            handler_entered.set()
            assert release_handler.wait(timeout=5.0)

    handler = BlockingHandler()
    watch = observer.schedule(handler, "/path/to/watch", recursive=True)
    observer.start()

    t: threading.Thread | None = None
    try:
        observer.event_queue.put((FileModifiedEvent("/path/to/watch/file.txt"), watch))
        assert handler_entered.wait(timeout=5.0), "Handler was not invoked"

        # While handler is executing, calling schedule from another thread must not deadlock
        def background_schedule():
            new_watch = observer.schedule(FileSystemEventHandler(), "/another/path")
            observer.unschedule(new_watch)
            schedule_succeeded.set()

        t = threading.Thread(target=background_schedule)
        t.start()
        t.join(timeout=5.0)
        assert schedule_succeeded.is_set(), "Concurrent schedule/unschedule was blocked by running handler"
    finally:
        release_handler.set()
        if t is not None:
            t.join(timeout=5.0)
        observer.stop()
        observer.join(timeout=5.0)


def test_observer_start_and_schedule_race() -> None:
    """Deterministically verify concurrent schedule() blocks on lock until start() completes.

    Addresses race condition #1044:
    1. HookedObserver pauses inside on_thread_start() while holding self._lock,
       before threading.Thread.start() has been called (is_alive() is False).
    2. An instrumented lock notifies the test the moment schedule() attempts acquisition.
    3. The test confirms schedule() has actively attempted acquire() and is blocked.
    4. Once startup resumes and completes, observer.is_alive() becomes True,
       schedule() acquires the lock and starts the emitter.
    """
    startup_reached = threading.Event()
    resume_startup = threading.Event()
    schedule_lock_attempted = threading.Event()
    schedule_finished = threading.Event()

    class HookedObserver(BaseObserver):
        def on_thread_start(self) -> None:
            super().on_thread_start()
            startup_reached.set()
            assert resume_startup.wait(timeout=2.0), "Timeout waiting to resume startup"

    class FastEmitter(EventEmitter):
        def __init__(self, *args, **kwargs):
            kwargs["timeout"] = 0.005
            super().__init__(*args, **kwargs)

        def queue_events(self, timeout: float) -> None:
            time.sleep(0.005)

    observer = HookedObserver(FastEmitter, timeout=0.005)
    real_lock = observer._lock  # noqa: SLF001

    class InstrumentedLock:
        def acquire(self, *args, **kwargs):
            if threading.current_thread() is t_sched:
                schedule_lock_attempted.set()
            return real_lock.acquire(*args, **kwargs)

        def release(self):
            real_lock.release()

        def __enter__(self):
            return self.acquire()

        def __exit__(self, *args):
            self.release()

        def __getattr__(self, name):
            return getattr(real_lock, name)

    observer._lock = InstrumentedLock()  # type: ignore[assignment]  # noqa: SLF001

    def do_start() -> None:
        observer.start()

    def do_schedule() -> None:
        observer.schedule(FileSystemEventHandler(), "/path/deterministic")
        schedule_finished.set()

    t_start = threading.Thread(target=do_start)
    t_sched = threading.Thread(target=do_schedule)

    try:
        t_start.start()
        assert startup_reached.wait(timeout=2.0), "Startup hook was not reached"
        assert not observer.is_alive(), "Observer should not be alive before Thread.start()"

        # Launch schedule thread while observer is paused in start()
        t_sched.start()
        # Verify schedule() actually reached and attempted to acquire observer._lock
        assert schedule_lock_attempted.wait(timeout=2.0), "schedule() did not attempt lock acquisition"
        # Since t_start holds observer._lock, schedule() must not have finished
        assert not schedule_finished.is_set(), "schedule() completed prematurely while lock was held"

        # Unblock startup
        resume_startup.set()
        t_start.join(timeout=2.0)
        assert not t_start.is_alive(), "Start thread hung"
        assert observer.is_alive(), "Observer should now be alive"

        # schedule() should now acquire the lock and complete
        assert schedule_finished.wait(timeout=2.0), "schedule() failed to finish after startup"
        t_sched.join(timeout=1.0)
        assert not t_sched.is_alive(), "Schedule thread hung"

        emitters = list(observer.emitters)
        assert len(emitters) == 1, "Emitter was not created"
        assert emitters[0].is_alive(), "Scheduled emitter was not started (Issue #1044)"
    finally:
        resume_startup.set()
        if t_start.is_alive():
            t_start.join(timeout=1.0)
        if t_sched.is_alive():
            t_sched.join(timeout=1.0)
        observer.stop()
        observer.join(timeout=2.0)
