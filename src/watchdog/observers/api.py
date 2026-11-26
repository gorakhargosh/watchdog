from __future__ import annotations

import contextlib
import logging
import os
import queue
import threading
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemMovedEvent
from watchdog.utils import BaseThread
from watchdog.utils.bricks import _EMPTY, SkipRepeatsQueue

if TYPE_CHECKING:
    import types
    from collections.abc import Callable
    from typing import Any, Self

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.utils import Seconds

logger = logging.getLogger(__name__)

DEFAULT_EMITTER_TIMEOUT: Seconds = 1.0
DEFAULT_OBSERVER_TIMEOUT: Seconds = 1.0


class _DrainSentinel:
    """Internal FIFO barrier placed on the event queue to wait for prior events to dispatch.

    Uses default identity equality so ``SkipRepeatsQueue`` never deduplicates
    a sentinel against any other queued item.
    """

    __slots__ = ("completed", "done_event")

    def __init__(self) -> None:
        self.done_event = threading.Event()
        self.completed = False


class EventQueue(SkipRepeatsQueue):
    """Thread-safe event queue based on a special queue that skips adding
    the same event (:class:`watchdog.events.FileSystemEvent`) multiple times
    consecutively. Thus avoiding dispatching multiple event handling
    calls when multiple identical events are produced quicker than an observer
    can consume them.

    :param maxsize:
        Maximum number of items allowed in the queue. If <= 0, the queue size is infinite.
    :type maxsize:
        ``int``
    """

    def _discard_sentinel(self, sentinel: _DrainSentinel) -> bool:
        """Delete an unconsumed drain sentinel from the queue if it is still waiting.

        Called when the dispatcher thread exits before it could pop ``sentinel``,
        so the sentinel is not left sitting in the queue as an unfinished task.
        Returns ``True`` if the sentinel was found and removed, ``False`` if it
        had already been popped.
        """
        # self.mutex is queue.Queue's internal threading.Lock protecting self.queue
        # and self.unfinished_tasks from concurrent put()/get() calls.
        with self.mutex:
            for idx, item in enumerate(self.queue):
                if item is sentinel:
                    del self.queue[idx]
                    if self._last_item is sentinel:
                        self._last_item = self.queue[-1] if self.queue else _EMPTY
                    self.unfinished_tasks -= 1
                    if self.unfinished_tasks == 0:
                        self.all_tasks_done.notify_all()
                    self.not_full.notify()
                    return True
        return False


class ObservedWatch:
    """An scheduled watch.

    :param path:
        Path string.
    :type path:
        ``str`` or :class:`pathlib.Path`
    :param recursive:
        ``True`` if watch should include subdirectories; ``False`` otherwise.
    :type recursive:
        ``bool``
    :param event_filter:
        Optional collection of :class:`watchdog.events.FileSystemEvent` to watch.
    :type event_filter:
        Iterable[:class:`watchdog.events.FileSystemEvent`] | None
    :param follow_symlink:
        ``True`` if symlinks are followed; ``False`` otherwise.
    :type follow_symlink:
        ``bool``
    """

    def __init__(
        self,
        path: str | Path,
        *,
        recursive: bool,
        event_filter: list[type[FileSystemEvent]] | None = None,
        follow_symlink: bool = False,
    ):
        raw_path = str(path) if isinstance(path, Path) else path
        self.raw_path = raw_path
        self.follow_symlink = follow_symlink
        self.event_filter = frozenset(event_filter) if event_filter is not None else None

        self.is_file = os.path.isfile(raw_path)
        self.resolved_path = (
            os.path.realpath(os.path.abspath(raw_path)) if follow_symlink else os.path.abspath(raw_path)
        )

        if self.is_file:
            self.path = os.path.dirname(self.resolved_path)
            self.is_recursive = False
        else:
            self.path = raw_path
            self.is_recursive = recursive

    @property
    def key(self) -> tuple[str, bool, frozenset[type[FileSystemEvent]] | None, bool]:
        """A tuple key identifying the watch (raw_path, recursive, event_filter, follow_symlink)."""
        return self.raw_path, self.is_recursive, self.event_filter, self.follow_symlink

    def __eq__(self, watch: object) -> bool:
        if not isinstance(watch, ObservedWatch):
            return NotImplemented
        return self.key == watch.key

    def __ne__(self, watch: object) -> bool:
        if not isinstance(watch, ObservedWatch):
            return NotImplemented
        return self.key != watch.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        if self.event_filter is not None:
            event_filter_str = "|".join(sorted(_cls.__name__ for _cls in self.event_filter))
            event_filter_str = f", event_filter={event_filter_str}"
        else:
            event_filter_str = ""
        return f"<{type(self).__name__}: path={self.path!r}, is_recursive={self.is_recursive}{event_filter_str}>"


# Observer classes
class EventEmitter(BaseThread):
    """Producer thread base class subclassed by event emitters
    that generate events and populate a queue with them.

    :param event_queue:
        The event queue to populate with generated events.
    :type event_queue:
        :class:`EventQueue`
    :param watch:
        The watch to observe and produce events for.
    :type watch:
        :class:`ObservedWatch`
    :param timeout:
        Timeout between successive attempts at reading events.
    :type timeout:
        ``Seconds``
    :param event_filter:
        Collection of event types to emit, or None for no filtering (default).
    :type event_filter:
        Iterable[:class:`watchdog.events.FileSystemEvent`] | None
    """

    def __init__(
        self,
        event_queue: EventQueue,
        watch: ObservedWatch,
        *,
        timeout: Seconds = DEFAULT_EMITTER_TIMEOUT,
        event_filter: list[type[FileSystemEvent]] | None = None,
    ) -> None:
        super().__init__()
        # bool subclasses int; timeout=True would silently become 1.0s
        if isinstance(timeout, bool):
            error = f"timeout must be a float, not bool (got {timeout!r})"
            raise TypeError(error)
        self._event_queue = event_queue
        self._watch = watch
        self._timeout = timeout
        self._event_filter = frozenset(event_filter) if event_filter is not None else None
        self._exception: Exception | None = None
        self._on_exit: Callable[[EventEmitter, Exception | None], None] | None = None

    @property
    def timeout(self) -> Seconds:
        """Blocking timeout for reading events."""
        return self._timeout

    @property
    def watch(self) -> ObservedWatch:
        """The watch associated with this emitter."""
        return self._watch

    @property
    def exception(self) -> Exception | None:
        """The unhandled exception that terminated this emitter, if any."""
        return self._exception

    def _notify_exit(self, exc: Exception | None) -> None:
        callback = self._on_exit
        if callback is not None:
            try:
                callback(self, exc)
            except Exception:
                logger.exception("Error in emitter exit callback for %r", self.watch)

    def queue_event(self, event: FileSystemEvent) -> None:
        """Queues a single event.

        :param event:
            Event to be queued.
        :type event:
            An instance of :class:`watchdog.events.FileSystemEvent`
            or a subclass.
        """
        if self._event_filter is None or any(isinstance(event, cls) for cls in self._event_filter):
            self._event_queue.put((event, self.watch))

    def queue_events(self, timeout: Seconds) -> None:
        """Override this method to populate the event queue with events
        per interval period.

        :param timeout:
            Timeout between successive attempts at
            reading events.
        :type timeout:
            ``Seconds``
        """

    def run(self) -> None:
        exit_error: Exception | None = None
        try:
            while self.should_keep_running():
                self.queue_events(self.timeout)
        except Exception as exc:
            # Record ordinary emitter failures for lifecycle hooks / future supervision
            # while letting process-control BaseExceptions propagate untouched.
            exit_error = exc
            self._exception = exc
            raise
        finally:
            self._notify_exit(exit_error)


class EventDispatcher(BaseThread):
    """Consumer thread base class subclassed by event observer threads
    that dispatch events from an event queue to appropriate event handlers.

    :param timeout:
        Timeout value passed to emitters
        constructions in the child class BaseObserver.
    :type timeout:
        ``Seconds``
    """

    stop_event = object()
    """Event inserted into the queue to signal a requested stop."""

    def __init__(self, *, timeout: Seconds = DEFAULT_OBSERVER_TIMEOUT) -> None:
        super().__init__()
        # bool subclasses int; timeout=True would silently become 1.0s
        if isinstance(timeout, bool):
            error = f"timeout must be a float, not bool (got {timeout!r})"
            raise TypeError(error)
        self._event_queue = EventQueue()
        self._timeout = timeout
        self._drain_lock = threading.Lock()
        self._active_drain: _DrainSentinel | None = None
        self._dispatcher_exited = False

    @property
    def timeout(self) -> Seconds:
        """Timeout value to construct emitters with."""
        return self._timeout

    def stop(self) -> None:
        BaseThread.stop(self)
        with contextlib.suppress(queue.Full):
            self.event_queue.put_nowait(EventDispatcher.stop_event)

    @property
    def event_queue(self) -> EventQueue:
        """The event queue which is populated with file system events
        by emitters and from which events are dispatched by a dispatcher
        thread.
        """
        return self._event_queue

    def dispatch_events(self, event_queue: EventQueue) -> None:
        """Override this method to consume events from an event queue, blocking
        on the queue for the specified timeout before raising :class:`queue.Empty`.

        :param event_queue:
            Event queue to populate with one set of events.
        :type event_queue:
            :class:`EventQueue`
        :raises:
            :class:`queue.Empty`
        """

    def run(self) -> None:
        try:
            while self.should_keep_running():
                try:
                    self.dispatch_events(self.event_queue)
                except queue.Empty:
                    continue
        finally:
            # Wake any pending stop(drain=True) waiters with completed=False so they
            # never hang until drain_timeout if the dispatcher exits unexpectedly.
            with self._drain_lock:
                self._dispatcher_exited = True
                active = self._active_drain
                self._active_drain = None
            if active is not None:
                self.event_queue._discard_sentinel(active)  # noqa: SLF001
                active.done_event.set()
            if self.should_keep_running():
                # Unexpected dispatcher exit: tear down emitters so they don't keep
                # running as orphaned producer threads leaking into event_queue.
                try:
                    self.on_thread_stop()
                except Exception:
                    logger.exception("Error during dispatcher teardown")


class BaseObserver(EventDispatcher):
    """Base observer.

    :param emitter_class:
        The class of the emitter to use (e.g., a subclass of :class:`EventEmitter`).
    :type emitter_class:
        ``type[EventEmitter]``
    :param timeout:
        The timeout for the observer to wait on events.
    :type timeout:
        ``Seconds``
    :param kwargs:
        Extra keyword arguments forwarded to every emitter this observer
        constructs, for platform-specific emitter options.
    """

    def __init__(
        self,
        emitter_class: type[EventEmitter],
        *,
        timeout: Seconds = DEFAULT_OBSERVER_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self._emitter_class = emitter_class
        self._emitter_kwargs = kwargs
        self._lock = threading.RLock()
        self._watches: set[ObservedWatch] = set()
        self._handlers: defaultdict[ObservedWatch, set[FileSystemEventHandler]] = defaultdict(set)
        self._emitters: set[EventEmitter] = set()
        self._emitter_for_watch: dict[ObservedWatch, EventEmitter] = {}
        self._draining = False
        self._drain_completed: bool | None = None

    def _on_emitter_exit(self, emitter: EventEmitter, exc: Exception | None) -> None:
        """Internal lifecycle hook called when an emitter thread exits.

        Kept intentionally lightweight so subclasses/supervisors can observe
        emitter termination without joining or restarting from the emitter thread.
        """
        if exc is not None:
            logger.debug("Emitter for %r exited with exception: %r", emitter.watch, exc)

    def _add_emitter(self, emitter: EventEmitter) -> None:
        emitter._on_exit = self._on_emitter_exit  # noqa: SLF001
        self._emitter_for_watch[emitter.watch] = emitter
        self._emitters.add(emitter)

    def _stop_and_join_emitters(self, emitters: list[EventEmitter]) -> None:
        """Stop all given emitters first, then join them outside ``self._lock``.

        Stopping all emitters before joining lets them unblock concurrently
        rather than waiting sequentially for each emitter's poll timeout.
        """
        for emitter in emitters:
            # Guard against calling stop() twice on an already-stopped emitter.
            if emitter.should_keep_running():
                emitter.stop()
        for emitter in emitters:
            with contextlib.suppress(RuntimeError):
                emitter.join()

    def _remove_emitter(self, emitter: EventEmitter) -> None:
        del self._emitter_for_watch[emitter.watch]
        self._emitters.remove(emitter)
        if emitter.should_keep_running():
            emitter.stop()
        with contextlib.suppress(RuntimeError):
            emitter.join()

    def _detach_emitters(self) -> list[EventEmitter]:
        """Detach and return all emitters; caller must hold ``self._lock``."""
        emitters = list(self._emitters)
        self._emitters.clear()
        self._emitter_for_watch.clear()
        return emitters

    def _clear_emitters(self) -> None:
        """Detach all emitters under ``self._lock``, then stop and join them unlocked."""
        with self._lock:
            emitters = self._detach_emitters()
        self._stop_and_join_emitters(emitters)

    @property
    def drain_completed(self) -> bool | None:
        """Whether the most recent ``stop(drain=True)`` confirmed all queued events
        were dispatched before shutdown.

        Returns ``None`` if ``stop(drain=True)`` has not been called, ``True`` if the
        drain sentinel was processed by the dispatcher, or ``False`` if draining timed
        out, the dispatcher was not running, or ``stop(drain=True)`` was called from
        the dispatcher thread itself.
        """
        return self._drain_completed

    def _add_handler_for_watch(self, event_handler: FileSystemEventHandler, watch: ObservedWatch) -> None:
        self._handlers[watch].add(event_handler)

    def _remove_handlers_for_watch(self, watch: ObservedWatch) -> None:
        del self._handlers[watch]

    @property
    def emitters(self) -> set[EventEmitter]:
        """Returns event emitter created by this observer."""
        return self._emitters

    def start(self) -> None:
        """Starts the observer thread and all scheduled emitters under synchronization lock.

        Overrides :meth:`watchdog.utils.BaseThread.start` to guarantee atomicity between
        observer startup and concurrent :meth:`schedule` invocations (prevents #1044).
        """
        with self._lock:
            super().start()

    def on_thread_start(self) -> None:
        """Start all scheduled emitters before the observer thread begins dispatching."""
        with self._lock:
            for emitter in self._emitters.copy():
                try:
                    emitter.start()
                except Exception:
                    self._remove_emitter(emitter)
                    raise

    def __enter__(self) -> Self:
        """Context manager entry. Starts the observer if not already running."""
        if not self.is_alive():
            self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Context manager exit. Stops the observer and waits for it to finish."""
        if self.is_alive():
            self.stop()
            self.join()

    def schedule(
        self,
        event_handler: FileSystemEventHandler,
        path: str | Path,
        *,
        recursive: bool = False,
        event_filter: list[type[FileSystemEvent]] | None = None,
        follow_symlink: bool = False,
    ) -> ObservedWatch:
        """Schedules watching a path and calls appropriate methods specified
        in the given event handler in response to file system events.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param path:
            Directory or file path that will be monitored.
        :type path:
            ``str`` or :class:`pathlib.Path`
        :param recursive:
            ``True`` if events will be emitted for sub-directories
            traversed recursively; ``False`` otherwise.
        :type recursive:
            ``bool``
        :param event_filter:
            Collection of event types to emit, or None for no filtering (default).
        :type event_filter:
            Iterable[:class:`watchdog.events.FileSystemEvent`] | None
        :param follow_symlink:
            ``True`` if symlinks should be followed; ``False`` otherwise.
        :type follow_symlink:
            ``bool``
        :return:
            An :class:`ObservedWatch` object instance representing
            a watch.
        """
        with self._lock:
            if self._draining:
                error = "Cannot schedule a watch while the observer is draining"
                raise RuntimeError(error)

            watch = ObservedWatch(path, recursive=recursive, event_filter=event_filter, follow_symlink=follow_symlink)

            # If we don't have an emitter for this watch already, create it.
            if watch not in self._emitter_for_watch:
                emitter = self._emitter_class(
                    self.event_queue,
                    watch,
                    timeout=self.timeout,
                    event_filter=event_filter,
                    **self._emitter_kwargs,
                )
                # Register the emitter and its exit hook before starting so an
                # immediate failure in run() always sees a registered emitter.
                self._add_emitter(emitter)
                try:
                    if self.is_alive() and self.should_keep_running():
                        emitter.start()
                except BaseException:
                    self._remove_emitter(emitter)
                    raise
            self._add_handler_for_watch(event_handler, watch)
            self._watches.add(watch)
        return watch

    def add_handler_for_watch(self, event_handler: FileSystemEventHandler, watch: ObservedWatch) -> None:
        """Adds a handler for the given watch.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param watch:
            The watch to add a handler for.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            self._add_handler_for_watch(event_handler, watch)

    def remove_handler_for_watch(self, event_handler: FileSystemEventHandler, watch: ObservedWatch) -> None:
        """Removes a handler for the given watch.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param watch:
            The watch to remove a handler for.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            # Use .get() rather than indexing: _handlers is a defaultdict, so
            # indexing it here would resurrect a watch that unschedule() already
            # removed, leaving a permanent empty-set entry behind.
            self._handlers.get(watch, set()).remove(event_handler)

    def unschedule(self, watch: ObservedWatch) -> None:
        """Unschedules a watch.

        :param watch:
            The watch to unschedule.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            emitter = self._emitter_for_watch[watch]
            del self._handlers[watch]
            self._remove_emitter(emitter)
            self._watches.remove(watch)

    def unschedule_all(self) -> None:
        """Unschedules all watches and detaches all associated event handlers."""
        with self._lock:
            self._handlers.clear()
            self._watches.clear()
            emitters = self._detach_emitters()
        self._stop_and_join_emitters(emitters)

    def _drain_event_queue(self, drain_timeout: float | None) -> bool:
        """Stop all emitters and wait for already-queued events to finish dispatching.

        Returns ``True`` only when the dispatcher thread actually processes the
        FIFO drain sentinel, confirming all prior events were dispatched.
        """
        if drain_timeout is not None and (
            isinstance(drain_timeout, bool) or not isinstance(drain_timeout, (int, float))
        ):
            error = f"drain_timeout must be a float or None (got {drain_timeout!r})"
            raise TypeError(error)

        if threading.current_thread() is self:
            logger.warning("stop(drain=True) called from observer dispatch thread; skipping drain to avoid deadlock")
            return False

        # Mark draining under self._lock before snapshotting emitters so concurrent
        # schedule() calls cannot start new emitters outside the drain barrier.
        # Stop and join emitters outside self._lock while handlers remain registered,
        # so running handlers can still call schedule()/unschedule() without deadlocking.
        with self._lock:
            self._draining = True
            emitters = list(self._emitters)
        self._stop_and_join_emitters(emitters)

        if not self.is_alive():
            return False

        # Check exit state, coalesce concurrent drains onto one active sentinel, and
        # enqueue atomically under self._drain_lock.
        with self._drain_lock:
            if self._dispatcher_exited:
                return False
            if self._active_drain is None:
                self._active_drain = _DrainSentinel()
                self.event_queue.put(self._active_drain)
            sentinel = self._active_drain

        sentinel.done_event.wait(timeout=drain_timeout)
        return sentinel.completed

    def stop(self, *, drain: bool = False, drain_timeout: float | None = None) -> None:
        """Signals the observer to stop.

        Draining must occur here rather than in :meth:`on_thread_stop` because
        :meth:`watchdog.utils.BaseThread.stop` sets ``_stopped_event`` first, which
        immediately ends the dispatcher loop.

        :param drain:
            If ``True``, stops and joins all active emitters first so no new OS
            events are produced, waits for already-queued events to be dispatched
            to registered handlers, and then clears handlers and stops the
            dispatcher thread. Defaults to ``False`` (immediate stop).
        :param drain_timeout:
            Maximum time in seconds to wait for queued events to drain after
            emitters have stopped when ``drain=True`` (does not bound emitter
            shutdown/join time). ``None`` (the default) waits indefinitely with
            no deadline. Ignored when ``drain=False``.
        """
        self._drain_completed = self._drain_event_queue(drain_timeout) if drain else None
        super().stop()

    def on_thread_stop(self) -> None:
        self.unschedule_all()

    def dispatch_events(self, event_queue: EventQueue) -> None:
        entry = event_queue.get(block=True)
        try:
            # Fast-path ordinary (event, watch) tuples past control-item checks.
            if type(entry) is not tuple:
                if entry is EventDispatcher.stop_event:
                    return
                if isinstance(entry, _DrainSentinel):
                    entry.completed = True
                    entry.done_event.set()
                    return

            event, watch = entry

            if watch.is_file:
                target = watch.resolved_path
                src_path = (
                    os.path.realpath(os.path.abspath(event.src_path))
                    if watch.follow_symlink
                    else os.path.abspath(event.src_path)
                )
                dest_path = None
                if isinstance(event, FileSystemMovedEvent) and event.dest_path:
                    dest_path = (
                        os.path.realpath(os.path.abspath(event.dest_path))
                        if watch.follow_symlink
                        else os.path.abspath(event.dest_path)
                    )
                if src_path != target and dest_path != target:
                    return

            # To allow unschedule/stop and safe removal of event handlers
            # within event handlers itself, check if the handler is still
            # registered before dispatching.
            # Use .get() rather than indexing: _handlers is a defaultdict, so
            # indexing it here would resurrect a watch that unschedule() removed
            # but whose events were already queued.
            # Handlers are dispatched without holding self._lock to avoid blocking
            # concurrent calls to schedule(), unschedule(), or stop().
            with self._lock:
                handlers = list(self._handlers.get(watch, ()))

            for handler in handlers:
                with self._lock:
                    is_active = handler in self._handlers.get(watch, ())
                if is_active:
                    event.watch_path = watch.path
                    handler.dispatch(event)
        finally:
            event_queue.task_done()
