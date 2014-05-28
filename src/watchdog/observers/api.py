#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
:module: watchdog.observers.api
:synopsis: Classes useful to observer implementers.
:author: yesudeep@google.com (Yesudeep Mangalapilly)

Immutables
----------
.. autoclass:: ObservedWatch
   :members:
   :show-inheritance:


Collections
-----------
.. autoclass:: EventQueue
   :members:
   :show-inheritance:

Classes
-------
.. autoclass:: EventEmitter
   :members:
   :show-inheritance:

.. autoclass:: EventDispatcher
   :members:
   :show-inheritance:

.. autoclass:: BaseObserver
   :members:
   :show-inheritance:
"""

from __future__ import with_statement
import threading
from watchdog.utils import DaemonThread
from watchdog.utils.compat import queue
from watchdog.utils.bricks import SkipRepeatsQueue

DEFAULT_EMITTER_TIMEOUT = 1    # in seconds.
DEFAULT_OBSERVER_TIMEOUT = 1   # in seconds.


# Collection classes
class EventQueue(SkipRepeatsQueue):

    """Thread-safe event queue based on a special queue that skips adding
    the same event (:class:`FileSystemEvent`) multiple times consecutively.
    Thus avoiding dispatching multiple event handling
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
    def key(self):
        return self.path, self.is_recursive

    def __eq__(self, watch):
        return self.key == watch.key

    def __ne__(self, watch):
        return self.key != watch.key

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return "<ObservedWatch: path=%s, is_recursive=%s>" % (
            self.path, self.is_recursive)


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
    :param timeout:
        Timeout (in seconds) between successive attempts at reading events.
    :type timeout:
        ``float``
    """

    def __init__(self, event_queue, watch, timeout=DEFAULT_EMITTER_TIMEOUT):
        DaemonThread.__init__(self)
        self._event_queue = event_queue
        self._watch = watch
        self._timeout = timeout

    @property
    def timeout(self):
        """
        Blocking timeout for reading events.
        """
        return self._timeout

    @property
    def watch(self):
        """
        The watch associated with this emitter.
        """
        return self._watch

    def queue_event(self, event):
        """
        Queues a single event.

        :param event:
            Event to be queued.
        :type event:
            An instance of :class:`watchdog.events.FileSystemEvent`
            or a subclass.
        """
        self._event_queue.put((event, self.watch))

    def queue_events(self, timeout):
        """Override this method to populate the event queue with events
        per interval period.

        :param timeout:
            Timeout (in seconds) between successive attempts at
            reading events.
        :type timeout:
            ``float``
        """

    def run(self):
        try:
            while self.should_keep_running():
                self.queue_events(self.timeout)
        finally:
            pass


class EventDispatcher(DaemonThread):

    """
    Consumer daemon thread base class subclassed by event observer threads
    that dispatch events from an event queue to appropriate event handlers.

    :param timeout:
        Event queue blocking timeout (in seconds).
    :type timeout:
        ``float``
    """

    def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
        DaemonThread.__init__(self)
        self._event_queue = EventQueue()
        self._timeout = timeout

    @property
    def timeout(self):
        """Event queue block timeout."""
        return self._timeout

    @property
    def event_queue(self):
        """The event queue which is populated with file system events
        by emitters and from which events are dispatched by a dispatcher
        thread."""
        return self._event_queue

    def dispatch_events(self, event_queue, timeout):
        """Override this method to consume events from an event queue, blocking
        on the queue for the specified timeout before raising :class:`queue.Empty`.

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

    def run(self):
        while self.should_keep_running():
            try:
                self.dispatch_events(self.event_queue, self.timeout)
            except queue.Empty:
                continue


class BaseObserver(EventDispatcher):

    """Base observer."""

    def __init__(self, emitter_class, timeout=DEFAULT_OBSERVER_TIMEOUT):
        EventDispatcher.__init__(self, timeout)
        self._emitter_class = emitter_class
        self._lock = threading.Lock()
        self._watches = set()
        self._handlers = dict()
        self._emitters = set()
        self._emitter_for_watch = dict()

    def _add_emitter(self, emitter):
        self._emitter_for_watch[emitter.watch] = emitter
        self._emitters.add(emitter)

    def _remove_emitter(self, emitter):
        del self._emitter_for_watch[emitter.watch]
        self._emitters.remove(emitter)
        emitter.stop()

    def _get_emitter_for_watch(self, watch):
        return self._emitter_for_watch[watch]

    def _clear_emitters(self):
        for emitter in self._emitters:
            emitter.stop()
        self._emitters.clear()
        self._emitter_for_watch.clear()

    def _add_handler_for_watch(self, event_handler, watch):
        try:
            self._handlers[watch].add(event_handler)
        except KeyError:
            self._handlers[watch] = set([event_handler])

    def _get_handlers_for_watch(self, watch):
        return self._handlers[watch]

    def _remove_handlers_for_watch(self, watch):
        del self._handlers[watch]

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
                                              timeout=self.timeout)
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

    def on_thread_stop(self):
        self.unschedule_all()

    def _dispatch_event(self, event, watch):
        with self._lock:
            for handler in self._get_handlers_for_watch(watch):
                handler.dispatch(event)

    def dispatch_events(self, event_queue, timeout):
        event, watch = event_queue.get(block=True, timeout=timeout)
        try:
            self._dispatch_event(event, watch)
        except KeyError:
            # All handlers for the watch have already been removed. We cannot
            # lock properly here, because `event_queue.get` blocks whenever the
            # queue is empty.
            pass
        event_queue.task_done()
