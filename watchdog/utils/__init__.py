# -*- coding: utf-8 -*-
# utils.py: Utility functions.
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
    :module: watchdog.utils
    :author: Gora Khargosh <gora.khargosh@gmail.com>
"""

import os
import os.path
import sys
import threading

from fnmatch import fnmatch

def has_attribute(ob, attribute):
    """hasattr swallows exceptions. This one tests a Python object for the
    presence of an attribute."""
    return getattr(ob, attribute, None) is not None


class DaemonThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        if has_attribute(self, 'daemon'):
            self.daemon = True
        else:
            self.setDaemon(True)
        self._stopped_event = threading.Event()

        if not has_attribute(self._stopped_event.is_set, 'is_set'):
            self._stopped_event.is_set = self._stopped_event.isSet

    @property
    def stopped_event(self):
        return self._stopped_event

    def should_stop(self):
        """Determines whether the daemon thread should stop."""
        return self._stopped_event.is_set()

    def should_keep_running(self):
        """Determines whether the daemon thread should continue running."""
        return not self._stopped_event.is_set()

    def on_told_to_stop(self):
        """Override this method instead of :meth:`stop()`.
        :meth:`stop()` calls this method.

        Note that this method is called immediately after the daemon thread
        is signaled to halt.
        """
        pass

    def stop(self):
        """Signals the daemon thread to stop."""
        self._stopped_event.set()
        self.on_stopping()


if not has_attribute(DaemonThread, 'is_alive'):
    DaemonThread.is_alive = DaemonThread.isAlive


class EventEmitter(DaemonThread):
    """
    Producer daemon thread base class subclassed by event emitters
    that generate events and populate a queue with them.

    :param path:
        The path to observe and produce events for.
    :type path:
        ``str``
    :param event_queue:
        The event queue to populate with generated events.
    :type event_queue:
        :class:`watchdog.events.EventQueue`
    :param recursive:
        ``True`` if events will be emitted for sub-directories
        traversed recursively; ``False`` otherwise.
    :type recursive:
        ``bool``
    :param interval:
        Interval period (in seconds) between successive attempts at reading events.
    :type interval:
        ``float``
    """
    def __init__(self, path, event_queue,
                 recursive=False, interval=1):
        DaemonThread.__init__(self, interval)

        self._lock = threading.Lock()
        self._path = real_absolute_path(path)
        self._event_queue = event_queue
        self._is_recursive = recursive
        self._interval = interval

    @property
    def interval(self):
        return self._interval

    @property
    def lock(self):
        return self._lock

    @property
    def is_recursive(self):
        return self._is_recursive

    @property
    def event_queue(self):
        return self._event_queue

    @property
    def path(self):
        return self._path

    def queue_events(self, event_queue, recursive, interval):
        """Override this method to populate the event queue with events
        per interval period.

        :param event_queue:
            Event queue to populate with one set of events.
        :type event_queue:
            :class:`watchdog.events.EventQueue`
        :param recursive:
            ``True`` if events will be emitted for sub-directories
            traversed recursively; ``False`` otherwise.
        :type recursive:
            ``bool``
        :param interval:
            Interval period (in seconds) between successive attempts at reading events.
        :type interval:
            ``float``
        """
        raise NotImplementedError()

    def on_exit(self):
        """Override this method for cleaning up immediately before the daemon
        thread stops completely."""

    def run(self):
        while self.should_keep_running():
            self.queue_events(self.event_queue, self.recursive, self.interval)
        self.on_exit()


class ObserverMixin(object):
    def schedule(self, name, event_handler, paths, recursive=False):
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
        raise NotImplementedError()

    def unschedule(self, *names):
        """Unschedules watching all the paths specified for a given names
        and detaches all associated event handlers.

        :param names:
            A list of identifying names to un-watch.
        """
        raise NotImplementedError()

    def unschedule_all(self):
        """Unschedules all watches and detaches all associated event
        handlers."""
        raise NotImplementedError()

    def create_event_emitter_instance(self, path, handler, \
                                      event_queue, recursive, interval):
        """Factory method to create and return an instance of an
        :class:`EventEmitter` thread."""


class EventDispatcher(DaemonThread, ObserverMixin):
    """
    Consumer daemon thread base class subclassed by event observer threads
    that dispatches events from an event queue to appropriate event handlers.

    :param interval:
        Interval period (in seconds) between successive attempts at dispatching
        events.
    :type interval:
        ``float``
    """
    def __init__(self, interval=1):
        DaemonThread.__init__(self, interval)

        self._lock = threading.Lock()
        self._event_queue = EventQueue()
        self._interval = interval

    @property
    def interval(self):
        return self._interval

    @property
    def lock(self):
        return self._lock

    @property
    def event_queue(self):
        return self._event_queue

    def dispatch_event(self, event):
        """Override this method to dispatch an individual event.

        :param event:
            Event to be dispatched.
        :type event:
            An instance of a subclass of
            :class:`watchdog.events.FileSystemEvent`
        """
        raise NotImplementedError()

    def _dispatch_events(self, event_queue, timeout):
        """Consumes events from an event queue. Blocks but waits for a specified
        timeout, before raising :class:`queue.Empty`.

        :param event_queue:
            Event queue to populate with one set of events.
        :type event_queue:
            :class:`watchdog.events.EventQueue`
        :param timeout:
            Interval period (in seconds) to wait before timing out on the
            event queue.
        :type timeout:
            ``float``
        :raises:
            :class:`queue.Empty`
        """
        event = event_queue.get(block=True, timeout=timeout)
        self.dispatch_event(event)
        event_queue.task_done()

    def on_exit(self):
        """Override this method for cleaning up immediately before the daemon
        thread stops completely."""

    def run(self):
        while self.should_keep_running():
            try:
                self._dispatch_events(self.event_queue, self.interval)
            except queue.Empty:
                continue
        self.on_exit()



def match_patterns(pathname, patterns):
    """Returns True if the pathname matches any of the given patterns."""
    for pattern in patterns:
        if fnmatch(pathname, pattern):
            return True
    return False


def match_allowed_and_ignored_patterns(pathname, allowed_patterns, ignore_patterns):
    return match_patterns(pathname, allowed_patterns) and not match_patterns(pathname, ignore_patterns)


def filter_paths(pathnames, patterns=["*"], ignore_patterns=[]):
    """Filters from a set of paths based on acceptable patterns and
    ignorable patterns."""
    result = []
    if patterns is None:
        patterns = []
    if ignore_patterns is None:
        ignore_patterns = []
    for path in pathnames:
        if match_patterns(path, patterns) and not match_patterns(path, ignore_patterns):
            result.append(path)
    return result


def load_module(module_name):
    """Imports a module given its name and returns a handle to it."""
    try:
        __import__(module_name)
    except ImportError:
        raise ImportError('No module named %s' % module_name)
    return sys.modules[module_name]


def load_class(dotted_path, *args, **kwargs):
    """Loads and returns a class definition provided a dotted path
    specification the last part of the dotted path is the class name
    and there is at least one module name preceding the class name.

    Notes:
    You will need to ensure that the module you are trying to load
    exists in the Python path.

    Examples:
    - module.name.ClassName    # Provided module.name is in the Python path.
    - module.ClassName         # Provided module is in the Python path.

    What won't work:
    - ClassName
    - modle.name.ClassName     # Typo in module name.
    - module.name.ClasNam      # Typo in classname.
    """
    dotted_path_split = dotted_path.split('.')
    if len(dotted_path_split) > 1:
        klass_name = dotted_path_split[-1]
        module_name = '.'.join(dotted_path_split[:-1])

        module = load_module(module_name)
        if has_attribute(module, klass_name):
            klass = getattr(module, klass_name)
            return klass
            # Finally create and return an instance of the class
            #return klass(*args, **kwargs)
        else:
            raise AttributeError('Module %s does not have class attribute %s' % (module_name, klass_name))
    else:
        raise ValueError('Dotted module path %s must contain a module name and a classname' % dotted_path)


def read_text_file(file_path, mode='rb'):
    """Returns the contents of a file after opening it in read-only mode."""
    return open(file_path, mode).read()


def get_walker(recursive=False):
    """Returns a recursive or a non-recursive directory walker."""
    if recursive:
        walk = os.walk
    else:
        def walk(path):
            try:
                yield next(os.walk(path))
            except NameError:
                yield os.walk(path).next()
    return walk



def absolute_path(path):
    return os.path.abspath(os.path.normpath(path))


def real_absolute_path(path):
    return os.path.realpath(absolute_path(path))


def get_parent_dir_path(path):
    return absolute_path(os.path.dirname(path))

