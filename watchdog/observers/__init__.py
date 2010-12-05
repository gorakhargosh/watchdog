# -*- coding: utf-8 -*-
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
    :module: watchdog.observers
    :author: Gora Khargosh <gora.khargosh@gmail.com>
"""

from __future__ import with_statement

#import logging
import sys
import threading

from watchdog.utils import DaemonThread, real_absolute_path, has_attribute
#logging.basicConfig(level=logging.DEBUG)


try:
    import pyinotify
    #logging.debug('Using InotifyObserver.')
    from watchdog.observers.inotify_observer import InotifyObserver as _Observer
except ImportError:
    try:
        import _watchdog_fsevents
        from watchdog.observers.fsevents_observer import FSEventsObserver as _Observer
        #logging.debug('Using FSEventsObserver.')
    except ImportError:
        import select
        if has_attribute(select, 'kqueue') and sys.version_info > (2, 6, 0):
            from watchdog.observers.kqueue_observer import KqueueObserver as _Observer
            #logging.debug('Using KqueueObserver.')
        else:
            try:
                import select_backport as select
                from watchdog.observers.kqueue_observer import KqueueObserver as _Observer
                #logging.debug('Using KqueueObserver from `select_backport`')
            except ImportError:
                try:
                    import win32file
                    import win32con
                    #logging.debug('Using Win32Observer.')
                    #from watchdog.observers.win32_observer import Win32Observer as Observer
                    from watchdog.observers.win32ioc_observer import Win32IOCObserver as _Observer
                except ImportError:
                    #logging.debug('Using PollingObserver as fallback.')
                    from watchdog.observers.polling_observer import PollingObserver as _Observer

class Observer(_Observer):
    """
    Observer thread that allows scheduling event handling
    for specified paths without blocking the main thread of the callee
    Python program.

    :param interval:
        Interval (in seconds) to check for events.
    :type interval:
        ``float``
    """
    def __init__(self, interval=1):
        _Observer.__init__(self, interval=interval)

    def schedule(self, name, event_handler, paths=None, recursive=False):
        """
        Schedules watching all the paths and calls appropriate methods specified
        in the given event handler in response to file system events.

        :param name:
            A unique symbolic name used to identify this set of paths and the
            associated event handler. This identifier is used to unschedule
            watching using the :meth:`Observer.unschedule` method.
        :type name:
            ``str``
        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param paths:
            A list of directory paths that will be monitored.
        :type paths:
            an iterable, for example, a ``list`` or ``set``, of ``str``
        :param recursive:
            ``True`` if events will be emitted for sub-directories
            traversed recursively; ``False`` otherwise.
        :type recursive:
            ``bool``
        """
        _Observer.schedule(self, name, event_handler, paths, recursive)

    def unschedule(self, *names):
        """Unschedules watching all the paths specified for a given names
        and detaches all associated event handlers.

        :param names:
            A list of identifying names to un-watch.
        """
        _Observer.unschedule(self, *names)


    def stop(self):
        """Stops all event monitoring for an :class:`Observer` instance."""
        _Observer.stop(self)


    def run(self):
        while not self.is_stopped:
            try:
                event = self.event_queue.get(block=True, timeout=self.interval)
                self.dispatch_event(event)
                self.event_queue.task_done()
            except queue.Empty:
                continue
        self.on_exit()


def _watch(event_handler, paths, recursive=False, main_callback=None):
    """A simple way to watch paths. Private API at the moment."""
    import uuid

    observer = Observer()
    if main_callback is None:
        def main_callback():
            import time
            while True:
                time.sleep(1)

    identifier = uuid.uuid1().hex
    observer.schedule(identifier, event_handler, paths, recursive)
    observer.start()
    try:
        main_callback()
    except KeyboardInterrupt:
        observer.unschedule(identifier)
        observer.stop()
    observer.join()
