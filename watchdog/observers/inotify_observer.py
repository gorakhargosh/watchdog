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

import sys

if sys.platform.startswith('linux'):
    import time
    import os.path
    import threading
    try:
        import queue
    except ImportError:
        import Queue as queue

    from pyinotify import ALL_EVENTS, \
        ProcessEvent, WatchManager, ThreadedNotifier

    from watchdog.utils import DaemonThread, absolute_path, real_absolute_path
    from watchdog.utils.collections import OrderedSetQueue
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
        EVENT_TYPE_MODIFIED


    def check_kwargs(kwargs, arg, method):
        if not arg in kwargs:
            raise ValueError('`%s` argument to method %s is not specified.' % arg, method)


    class _ProcessEventDispatcher(ProcessEvent):
        """ProcessEvent subclasses that dispatches events to our
        FileSystemEventHandler implementation."""
        def my_init(self, **kwargs):
            check_kwargs(kwargs, 'handlers', 'my_init')
            check_kwargs(kwargs, 'event_queue', 'my_init')
            check_kwargs(kwargs, 'recursive', 'my_init')

            self._event_queue = kwargs['event_queue']
            self._is_recursive = kwargs['recursive']
            self._handlers = kwargs['handlers']


        def process_IN_CREATE(self, event):
            src_path = absolute_path(event.pathname)
            if event.dir:
                self._event_queue.put(DirCreatedEvent(src_path))
            else:
                self._event_queue.put(FileCreatedEvent(src_path))


        def process_IN_DELETE(self, event):
            src_path = absolute_path(event.pathname)
            if event.dir:
                self._event_queue.put(DirDeletedEvent(src_path))
            else:
                self._event_queue.put(FileDeletedEvent(src_path))


        def process_IN_CLOSE_WRITE(self, event):
            src_path = absolute_path(event.pathname)
            if event.dir:
                self._event_queue.put(DirModifiedEvent(src_path))
            else:
                self._event_queue.put(FileModifiedEvent(src_path))


        def process_IN_ATTRIB(self, event):
            self.process_IN_CLOSE_WRITE(event)


        def process_IN_MOVED_TO(self, event):
            src_path = absolute_path(event.src_pathname)
            dest_path = absolute_path(event.pathname)

            if event.dir:
                dir_moved_event = DirMovedEvent(src_path, dest_path)
                if self._is_recursive:
                    for sub_moved_event in dir_moved_event.sub_moved_events():
                        self._event_queue.put(sub_moved_event)
                self._event_queue.put(dir_moved_event)
            else:
                self._event_queue.put(FileMovedEvent(src_path, dest_path))


    class _Watch(object):
        def __init__(self, group_name, notifier, descriptors):
            self.group_name = group_name
            self.descriptors = descriptors
            self.notifier = notifier


    class InotifyObserver(DaemonThread):
        """Inotify-based daemon observer thread for Linux."""
        def __init__(self, interval=1):
            super(InotifyObserver, self).__init__(interval)

            self._lock = threading.Lock()

            # Pyinotify watch manager.
            self._wm = WatchManager()

            # Set of all notifiers spawned.
            self._notifiers = set()

            # Set of all the watches.
            self._watches = set()

            # Watch objects for a given name.
            self._watches_for_name = {}

            # Event queue buffer.
            self._event_queue = EventQueue()



        def _remove_watch(self, watch):
            self._wm.rm_watch(watch.descriptor.values())
            watch.notifier.stop()
            self._notifiers.remove(watch.notifier)
            self._watches.remove(watch)
            self._watches_for_name[watch.group_name].remove(watch)


        def _remove_watches(self, watches):
            for watch in watches:
                self._remove_watch(watch)


        def schedule(self, name, event_handler, paths=None, recursive=False):
            """Schedules monitoring."""
            if not paths:
                raise ValueError('Please specify a few paths.')
            if isinstance(paths, basestring):
                paths = [paths]

            with self._lock:
                if name in _watch_for_name:
                    raise ValueError("Duplicate watch entry named '%s'" % name)

                self._watches_for_name[name] = set()
                for path in paths:
                    if not isinstance(path, basestring):
                        raise TypeError("Path must be string, not '%s'." % type(path).__name__)
                    if not os.path.isdir(path):
                        raise ValueError("Path '%s' is not a directory." % path)

                    path = real_absolute_path(path)
                    dispatcher = _ProcessEventDispatcher(handlers=set([event_handler]),
                                                         recursive=recursive,
                                                         event_queue=self._event_queue)
                    notifier = ThreadedNotifier(self._wm, dispatcher)
                    descriptors = self._wm.add_watch(path, ALL_EVENTS, rec=recursive, auto_add=True)

                    # Book-keeping
                    watch = _Watch(group_name, notifier, descriptors)
                    self._notifiers.add(notifier)
                    self._watches.add(watch)
                    self._watches_for_name[name].add(watch)

                    notifier.start()


        def unschedule(self, *names):
            with self._lock:
                for name in names:
                    try:
                        self._remove_watches(self._watches_for_name[name])
                    except KeyError:
                        raise KeyError("Watch named '%s' not found." % name)


        def run(self):
            while not self.is_stopped:
                #time.sleep(self.interval)
                try:
                    event = self._event_queue.get(block=True, timeout=self.interval)
                    event.dispatch()
                    self._event_queue.task_done()
                except queue.Empty:
                    continue
            self._clean_up()


        def _clean_up(self):
            for watch in self._watches:
                self._remove_watch(watch)
