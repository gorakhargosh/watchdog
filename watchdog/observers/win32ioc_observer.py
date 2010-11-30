# -*- coding: utf-8 -*-
# win32ioc_observer.py: I/O Completion + ReadDirectoryChangesW-based observer
# implementation for Windows.
#
# Copyright (C) 2010 Luke McCarthy <luke@iogopro.co.uk>
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
import os
import os.path
import stat
import ctypes
import pywintypes
import threading
try:
    import queue
except ImportError:
    import Queue as queue

from watchdog.events import EventQueue
from watchdog.utils import DaemonThread, real_absolute_path, absolute_path
from watchdog.observers.w32_api import *


class _Watch(object):
    def __init__(self, cookie, group_name, event_handler, path, recursive, buffer_size=BUFFER_SIZE):
        self._lock = threading.Lock()
        
        self.cookie = cookie
        self.group_name = group_name
        self.path = path
        self.is_recursive = recursive
        self.directory_handle = get_directory_handle(path, WATCHDOG_FILE_FLAGS_ASYNC)
        self.overlapped = pywintypes.OVERLAPPED()
        self.event_buffer_size = buffer_size
        self.event_buffer = ctypes.create_string_buffer(buffer_size)
        self.event_handler = event_handler
        self.is_removed = False

    def read_directory_changes(self):
        with self._lock:
            try:
                ReadDirectoryChangesW(self.directory_handle,
                                      self.event_buffer,
                                      self.is_recursive,
                                      WATCHDOG_FILE_NOTIFY_FLAGS,
                                      self.overlapped,
                                      None)
            except pywintypes.error, e:
                if e.args[0] == 5:
                    self.close()
                    # observer bookkeeping to remove watch.
                else:
                    raise

    def queue_events(self, num_bytes, out_event_queue):
        with self._lock:
            # queue events
            last_renamed_from_filename = ""
            for action, filename in FILE_NOTIFY_INFORMATION(self.event_buffer.raw, num_bytes):
                filename = absolute_path(os.path.join(self.path, filename))
    
                if action == FILE_ACTION_RENAMED_OLD_NAME:
                    last_renamed_from_filename = filename
                elif action == FILE_ACTION_RENAMED_NEW_NAME:
                    if os.path.isdir(filename):
                        src_dir_path = last_renamed_from_filename
                        dest_dir_path = filename
    
                        # Fire a moved event for the directory itself.
                        out_event_queue.put((self.event_handler, DirMovedEvent(src_dir_path, dest_dir_path)))
    
                        # Fire moved events for all files within this
                        # directory if recursive.
                        if self.is_recursive:
                            # HACK: We introduce a forced delay before
                            # traversing the moved directory. This will read
                            # only file movement that finishes within this
                            # delay time.
                            time.sleep(WATCHDOG_DELAY_BEFORE_TRAVERSING_MOVED_DIRECTORY)
                            # TODO: The following still does not execute because we need to wait for I/O to complete.
                            for moved_event in get_moved_events_for(src_dir_path, dest_dir_path, recursive=True):
                                out_event_queue.put((self.event_handler, moved_event))
                    else:
                        out_event_queue.put((self.event_handler, FileMovedEvent(last_renamed_from_filename, filename)))
                else:
                    if os.path.isdir(filename):
                        action_event_map = DIR_ACTION_EVENT_MAP
                    else:
                        action_event_map = FILE_ACTION_EVENT_MAP
                    out_event_queue.put((self.event_handler, action_event_map[action](filename)))


    def close(self):
        with self._lock:
            if self.directory_handle is not None:
                CancelIo(self.directory_handle)
                CloseHandle(self.directory_handle)
                self.directory_handle = None

    def remove(self):
        with self._lock:
            self.close()
            self.is_removed = True

    def associate_with_ioc_port(self, ioc_port):
        with self._lock:
            CreateIoCompletionPort(self.directory_handle, ioc_port, self.cookie, 0)


class Win32IOCObserver(DaemonThread):
    def __init__(self, interval=1, *args, **kwargs):
        super(Win32IOCObserver, self).__init__(interval=interval)

        self._lock = threading.RLock()

        self._args = args
        self._kwargs = kwargs
        self._q = EventQueue()

        self._map_name_to_cookies = {}
        self._map_cookie_to_watch = {}

        # Used to generate unique iokey cookies.
        self._cookie_counter = 0

        # Blank I/O completion port.
        self._ioc_timeout = interval * 1000
        self._ioc_port = create_io_completion_port()


    def _cookies_for_name(self, name):
        """Returns a list of all the cookies for a given name."""
        return self._map_name_to_cookies[name]

    def _watches_for_name(self, name):
        """Returns a list of all the watches for the given name."""
        watches = []
        for cookie in self.iokeys_for_name(name):
            watches.append(self._watch_for_cookie(cookie))
        return watches

    def _watch_for_cookie(self, cookie):
        """Returns the watch object for the given cookie."""
        return self._map_cookie_to_watch[cookie]

    def watches(self):
        """A list of all the watches."""
        return self._map_cookie_to_watches.values()


    def schedule(self, name, event_handler, paths, recursive=False):
        """Schedules monitoring specified paths and calls methods in the
        given callback handler based on events occurring in the file system.
        """
        if not paths:
            raise ValueError('Please specify a few paths.')
        if isinstance(paths, basestring):
            paths = [paths]

        with self._lock:
            self._map_name_to_cookies[name] = set()
            for path in paths:
                if not isinstance(path, basestring):
                    raise TypeError("Path must be string, not '%s'." % type(path).__name__)
                path = real_absolute_path(path)
                cookie = self._cookie_counter
                watch = _Watch(cookie, name, event_handler, path, recursive)
                self._cookie_counter += 1
                self._map_cookie_to_watch[cookie] = watch
                self._map_name_to_cookies[name].add(cookie)
                watch.associate_with_ioc_port(self._ioc_port)
                watch.read_directory_changes()


    def unschedule(self, *names):
        with self._lock:
            if not names:
                for watch in self.watches:
                    watch.remove()
                self._map_cookie_to_watch = {}
                self._map_name_to_cookies = {}
            else:
                for name in names:
                    if name in self._map_name_to_cookies:
                        for watch in self._watches_for_name(name):
                            watch.remove()
                            del self._map_cookie_to_watch[watch.cookie]
                            del self._map_name_to_cookies[name]


    def remove_cookie(self, cookie):
        with self._lock:
            watch = self.watch_for_key(cookie)
            del self._map_cookie_to_watch[cookie]
            self._map_name_to_cookies[watch.group_name].remove(cookie)
            watch.remove()


    def dispatch_events_for_cookie(self, cookie, num_bytes):
        with self._lock:
            watch = self._watch_for_cookie(cookie)
            if not watch.is_removed:
                watch.queue_events(num_bytes, self._q)
                while True:
                    try:
                        event_handler, event = self._q.get_nowait()
                        event_handler.dispatch(event)
                    except queue.Empty:
                        break
                watch.read_directory_changes()


    def run(self):
        while not self.is_stopped:
            # read status of io completion queue
            rc, num_bytes, cookie, _ = GetQueuedCompletionStatus(self._ioc_port, self._ioc_timeout)
            if rc == 0:
                # Successful.
                self.dispatch_events_for_cookie(cookie, num_bytes)
            elif rc == 5:
                # Error
                self.remove_cookie(self, cookie)

        # Clean up
        for watch in self.watches():
            watch.remove()
        if self._ioc_port is not None:
            CloseHandle(self._ioc_port)
            self._ioc_port = None

