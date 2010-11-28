# -*- coding: utf-8 -*-
# inotify_observer: Inotify-based observer implementation for Linux.
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

import time
import os.path

from pyinotify import ALL_EVENTS, \
    ProcessEvent, WatchManager, ThreadedNotifier

from watchdog.observers import DaemonThread
from watchdog.utils import absolute_path, real_absolute_path
from watchdog.decorator_utils import synchronized
from watchdog.events import \
    DirMovedEvent, \
    DirDeletedEvent, \
    DirCreatedEvent, \
    DirModifiedEvent, \
    FileMovedEvent, \
    FileDeletedEvent, \
    FileCreatedEvent, \
    FileModifiedEvent, \
    EVENT_TYPE_MOVED, \
    EVENT_TYPE_DELETED, \
    EVENT_TYPE_CREATED, \
    EVENT_TYPE_MODIFIED, \
    get_moved_events_for



def check_kwargs(kwargs, arg, method):
    if not arg in kwargs:
        raise ValueError('`%s` argument to method %s is not specified.' % arg, method)

class _ProcessEventDispatcher(ProcessEvent):
    """ProcessEvent subclasses that dispatches events to our
    FileSystemEventHandler implementation."""
    def my_init(self, **kwargs):
        check_kwargs(kwargs, 'event_handler', 'my_init')
        check_kwargs(kwargs, 'recursive', 'my_init')
        self.event_handler = kwargs['event_handler']
        self.is_recursive = kwargs['recursive']

    def process_IN_CREATE(self, event):
        src_path = absolute_path(event.pathname)
        if event.dir:
            self.event_handler.on_created(DirCreatedEvent(src_path))
        else:
            self.event_handler.on_created(FileCreatedEvent(src_path))


    def process_IN_DELETE(self, event):
        src_path = absolute_path(event.pathname)
        if event.dir:
            self.event_handler.on_deleted(DirDeletedEvent(src_path))
        else:
            self.event_handler.on_deleted(FileDeletedEvent(src_path))


    def process_IN_CLOSE_WRITE(self, event):
        src_path = absolute_path(event.pathname)
        if event.dir:
            self.event_handler.on_modified(DirModifiedEvent(src_path))
        else:
            self.event_handler.on_modified(FileModifiedEvent(src_path))


    def process_IN_ATTRIB(self, event):
        self.process_IN_CLOSE_WRITE(event)


    def process_IN_MOVED_TO(self, event):
        # TODO: Moved event on a directory does not fire moved event for
        # files inside the directory. Fix?
        src_path = absolute_path(event.src_pathname)
        dest_path = absolute_path(event.pathname)
        if event.dir:
            if self.is_recursive:
                for moved_event in get_moved_events_for(src_path, dest_path):
                    self.event_handler.on_moved(moved_event)
            self.event_handler.on_moved(DirMovedEvent(src_path, dest_path))
        else:
            self.event_handler.on_moved(FileMovedEvent(src_path, dest_path))


class _Rule(object):
    def __init__(self, name, notifier, descriptors):
        self.name = name
        self.notifier = notifier
        self.descriptors = descriptors


class InotifyObserver(DaemonThread):
    """Inotify-based daemon observer thread for Linux."""
    def __init__(self, interval=1):
        DaemonThread.__init__(self, interval)
        self.wm = WatchManager()
        self.notifiers = set()
        self.name_to_rule = dict()

    def on_stopping(self):
        for notifier in self.notifiers:
            notifier.stop()

    @synchronized()
    def schedule(self, name, event_handler, paths=None, recursive=False):
        """Schedules monitoring."""
        if not paths:
            raise ValueError('Please specify a few paths.')
        if isinstance(paths, basestring):
            paths = [paths]

        #from pyinotify import PrintAllEvents
        #dispatcher = PrintAllEvents()

        dispatcher = _ProcessEventDispatcher(event_handler=event_handler,
                                             recursive=recursive)
        notifier = ThreadedNotifier(self.wm, dispatcher)
        self.notifiers.add(notifier)
        for path in paths:
            if not isinstance(path, basestring):
                raise TypeError("Path must be string, not '%s'." % type(path).__name__)
            path = real_absolute_path(path)
            descriptors = self.wm.add_watch(path, ALL_EVENTS, rec=recursive, auto_add=True)
        self.name_to_rule[name] = _Rule(name, notifier, descriptors)
        notifier.start()


    @synchronized()
    def unschedule(self, *names):
        if not names:
            for name, rule in self.name_to_rule.items():
                self.wm.rm_watch(rule.descriptors.values())
        else:
            for name in names:
                rule = self.name_to_rule[name]
                self.wm.rm_watch(rule.descriptors.values())


    def run(self):
        while not self.is_stopped:
            time.sleep(self.interval)

