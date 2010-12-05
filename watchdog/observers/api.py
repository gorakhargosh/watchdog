# -*- coding: utf-8 -*-
# api.py: Observer, event emitter, and event queue API.
#
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
    :module: watchdog.observers.api
    :synopsis: Classes useful to observer implementers.
    :author: Gora Khargosh <gora.khargosh@gmail.com>
"""

from __future__ import with_statement
import threading
import functools
try:
    import queue
except ImportError:
    import Queue as queue

from watchdog.utils import DaemonThread
from watchdog.utils.collections import OrderedSetQueue

# Collection classes

class EventQueue(OrderedSetQueue):
    """Thread-safe event queue based on a thread-safe ordered-set queue
    to ensure duplicate :class:`FileSystemEvent` objects are prevented from
    adding themselves to the queue to avoid dispatching multiple event handling
    calls when multiple identical events are produced quicker than an observer
    can consume them.
    """

class ObservedWatch(object):
    """An scheduled watch.

    :param path:
        Path string.
    :param recursive:
        ``True`` if watch is recursive; ``False`` otherwise.
    """
    def __init__(self, path, recursive):
        self._path = path
        self._is_recursive = recursive

    @property
    def path(self):
        """The path that this watch monitors."""
        return self._path

    @property
    def is_recursive(self):
        """Determines whether subdirectories are watched for the path."""
        return self._is_recursive

    @property
    def signature(self):
        return self._key()

    def _key(self):
        return (self.path, self.is_recursive)

    def __eq__(self, watch):
        return self._key() == watch._key()

    def __ne__(self, watch):
        return self._key() != watch._key()

    def __hash__(self):
        return hash(self._key())

    def __repr__(self):
        return "<ObservedWatch: path=%s, is_recursive=%s>" % self.signature



# Observer classes
class EventEmitter(DaemonThread):
    """
    Producer daemon thread base class subclassed by event emitters
    that generate events and populate a queue with them.

    :param event_queue:
        The event queue to populate with generated events.
    :type event_queue:
        :class:`watchdog.events.EventQueue`
    :param watch:
        The watch to observe and produce events for.
    :type watch:
        :class:`ObservedWatch`
    :param interval:
        Interval period (in seconds) between successive attempts at reading events.
    :type interval:
        ``float``
    """
    def __init__(self, event_queue, watch, interval=1):
        DaemonThread.__init__(self)
        self._event_queue = event_queue
        self._watch = watch
        self._interval = interval

    @property
    def interval(self):
        return self._interval

    @property
    def watch(self):
        return self._watch

    def queue_events(self, event_queue, watch, interval):
        """Override this method to populate the event queue with events
        per interval period.

        :param event_queue:
            Event queue to populate with one set of events.
        :type event_queue:
            :class:`watchdog.events.EventQueue`
        :param watch:
            The watch to observe and produce events for.
        :type watch:
            :class:`ObservedWatch`
        :param interval:
            Interval period (in seconds) between successive attempts at reading events.
        :type interval:
            ``float``
        """

    def on_thread_exit(self):
        """Override this method for cleaning up immediately before the daemon
        thread stops completely."""

    def run(self):
        while self.should_keep_running():
            self.queue_events(self._event_queue, self.watch, self.interval)
        self.on_thread_exit()



class EventDispatcher(DaemonThread):
    """
    Consumer daemon thread base class subclassed by event observer threads
    that dispatch events from an event queue to appropriate event handlers.

    :param interval:
        Interval period (in seconds) between successive attempts at dispatching
        events.
    :type interval:
        ``float``
    """
    def __init__(self, interval=1):
        DaemonThread.__init__(self)
        self._event_queue = EventQueue()
        self._interval = interval

    @property
    def interval(self):
        """Event queue block timeout."""
        return self._interval

    @property
    def event_queue(self):
        """The event queue which is populated with file system events and from
        which events are dispatched."""
        return self._event_queue

    def dispatch_event(self, event, watch):
        """Override this method to dispatch an individual event.

        :param event:
            Event to be dispatched.
        :type event:
            An instance of a subclass of
            :class:`watchdog.events.FileSystemEvent`
        :param watch:
            The watch to dispatch for.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """

    def _dispatch_events(self, event_queue, timeout):
        """Consumes events from an event queue. Blocks on the queue for the
        specified timeout before raising :class:`queue.Empty`.

        :param event_queue:
            Event queue to populate with one set of events.
        :type event_queue:
            :class:`EventQueue`
        :param timeout:
            Interval period (in seconds) to wait before timing out on the
            event queue.
        :type timeout:
            ``float``
        :raises:
            :class:`queue.Empty`
        """
        event, watch = event_queue.get(block=True, timeout=timeout)
        self.dispatch_event(event, watch)
        event_queue.task_done()

    def on_thread_exit(self):
        """Override this method for cleaning up immediately before the daemon
        thread stops completely."""

    def run(self):
        while self.should_keep_running():
            try:
                self._dispatch_events(self.event_queue, self.interval)
            except queue.Empty:
                continue
        self.on_thread_exit()


class BaseObserver(EventDispatcher):
    """Base observer."""
    def __init__(self, emitter_class, interval=1):
        EventDispatcher.__init__(self, interval)
        self._emitter_class = emitter_class
        self._lock = threading.Lock()
        self._watches = set()
        self._handlers = dict()
        self._emitters = set()
        self._emitter_for_signature = dict()


    def _add_emitter(self, emitter):
        self._emitter_for_signature[emitter.watch.signature] = emitter
        self._emitters.add(emitter)

    def _remove_emitter(self, emitter):
        del self._emitter_for_signature[emitter.watch.signature]
        self._emitters.remove(emitter)
        emitter.stop()

    def _get_emitter_for_watch(self, watch):
        return self._emitter_for_signature[watch.signature]

    def _clear_emitters(self):
        for emitter in self._emitters:
            emitter.stop()
        self._emitters.clear()
        self._emitter_for_signature.clear()

    def _add_handler_for_watch(self, event_handler, watch):
        try:
            self._handlers[watch.signature].add(event_handler)
        except KeyError:
            self._handlers[watch.signature] = set([event_handler])

    def _get_handlers_for_watch(self, watch):
        return self._handlers[watch.signature]

    def _remove_handlers_for_watch(self, watch):
        del self._handlers[watch.signature]

    def _remove_handler_for_watch(self, handler, watch):
        handlers = self._get_handlers_for_watch(watch)
        handlers.remove(handler)


    def schedule(self, event_handler, path, recursive=False):
        """
        Schedules watching a path and calls appropriate methods specified
        in the given event handler in response to file system events.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param path:
            Directory path that will be monitored.
        :type path:
            ``str``
        :param recursive:
            ``True`` if events will be emitted for sub-directories
            traversed recursively; ``False`` otherwise.
        :type recursive:
            ``bool``
        :return:
            An :class:`ObservedWatch` object instance representing
            a watch.
        """
        with self._lock:
            watch = ObservedWatch(path, recursive)
            self._add_handler_for_watch(event_handler, watch)
            try:
                # If we have an emitter for this watch already, we don't create a
                # new emitter. Instead we add the handler to the event
                # object.
                emitter = self._get_emitter_for_watch(watch)
            except KeyError:
                # Create a new emitter and start it.
                emitter = self._emitter_class(event_queue=self.event_queue,
                                              watch=watch,
                                              interval=self.interval)
                self._add_emitter(emitter)
                emitter.start()
            self._watches.add(watch)
        return watch

    def add_handler_for_watch(self, event_handler, watch):
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

    def remove_handler_for_watch(self, event_handler, watch):
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
            self._remove_handler_for_watch(event_handler, watch)

    def unschedule(self, watch):
        """Unschedules a watch.

        :param watch:
            The watch to unschedule.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            try:
                emitter = self._get_emitter_for_watch(watch)
                self._remove_handlers_for_watch(watch)
                self._remove_emitter(emitter)
                self._watches.remove(watch)
            except KeyError:
                raise

    def unschedule_all(self):
        """Unschedules all watches and detaches all associated event
        handlers."""
        with self._lock:
            self._handlers.clear()
            self._clear_emitters()
            self._watches.clear()

    def on_thread_exit(self):
        self.unschedule_all()

    def dispatch_event(self, event, watch):
        with self._lock:
            for handler in self._get_handlers_for_watch(watch):
                handler._dispatch(event)
