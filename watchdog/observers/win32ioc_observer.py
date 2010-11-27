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
import os.path
import ctypes
import pywintypes

from watchdog.observers import DaemonThread
from watchdog.utils import get_walker
from watchdog.decorator_utils import synchronized
from watchdog.observers.w32_api import *


class _Watch(object):
    def __init__(self, iockey, group_name, event_handler, path, recursive, buffer_size=BUFFER_SIZE):
        self.iockey = iockey
        self.group_name = group_name
        self.path = path
        self.is_recursive = recursive
        self.directory_handle = get_directory_handle(path, WATCHDOG_FILE_FLAGS_ASYNC)
        self.overlapped = pywintypes.OVERLAPPED()
        self.event_buffer_size = buffer_size
        self.event_buffer = ctypes.create_string_buffer(buffer_size)
        self.event_handler = event_handler
        self.is_removed = False

    @synchronized()
    def read_directory_changes(self):
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

    @synchronized()
    def dispatch_events(self, num_bytes):
        # dispatch events
        last_renamed_from_filename = ""
        for action, filename in FILE_NOTIFY_INFORMATION(self.event_buffer.raw, num_bytes):
            filename = os.path.join(self.path, filename)
            if action == FILE_ACTION_RENAMED_OLD_NAME:
                last_renamed_from_filename = filename
            elif action == FILE_ACTION_RENAMED_NEW_NAME:
                if os.path.isdir(filename):
                    renamed_dir_path = last_renamed_from_filename.rstrip(os.path.sep)
                    new_dir_path = filename.rstrip(os.path.sep)

                    # Fire moved events for all files within this
                    # directory if recursive.
                    walk = get_walker(self.is_recursive)
                    if self.is_recursive:
                        # HACK: We introduce a forced delay before
                        # traversing the moved directory. This will read
                        # only file movement that finishes within this
                        # delay time.
                        time.sleep(WATCHDOG_DELAY_BEFORE_TRAVERSING_MOVED_DIRECTORY)
                        # TODO: The following still does not execute because we need to wait for I/O to complete.
                        for root, directories, filenames in walk(new_dir_path):
                            for d in directories:
                                full_path = os.path.join(root, d)
                                renamed_path = full_path.replace(new_dir_path, renamed_dir_path)
                                self.event_handler.dispatch(DirMovedEvent(renamed_path, full_path))
                            for f in filenames:
                                full_path = os.path.join(root, f)
                                renamed_path = full_path.replace(new_dir_path, renamed_dir_path)
                                self.event_handler.dispatch(FileMovedEvent(renamed_path, full_path))

                    # Fire a moved event for the directory itself.
                    self.event_handler.dispatch(DirMovedEvent(renamed_dir_path, new_dir_path))
                else:
                    self.event_handler.dispatch(FileMovedEvent(last_renamed_from_filename, filename))
            else:
                if os.path.isdir(filename):
                    action_event_map = DIR_ACTION_EVENT_MAP
                else:
                    action_event_map = FILE_ACTION_EVENT_MAP
                self.event_handler.dispatch(action_event_map[action](filename))

    @synchronized()
    def close(self):
        if self.directory_handle is not None:
            CancelIo(self.directory_handle)
            CloseHandle(self.directory_handle)
            self.directory_handle = None

    @synchronized()
    def remove(self):
        self.close()
        self.is_removed = True

    @synchronized()
    def associate_with_ioc_port(self, ioc_port):
        CreateIoCompletionPort(self.directory_handle, ioc_port, self.iockey, 0)


class Win32IOCObserver(DaemonThread):
    def __init__(self, interval=1, *args, **kwargs):
        DaemonThread.__init__(self)
        self.args = args
        self.kwargs = kwargs

        self.map_name_to_iockeys = {}
        self.map_iockey_to_watch = {}

        # Used to generate unique iokeys.
        self.iockey_counter = 0

        # Blank I/O completion port.
        self.interval = interval
        self.ioc_timeout = interval * 1000
        self.ioc_port = create_io_completion_port()


    @synchronized()
    def iockeys_for_name(self, name):
        """Returns a list of all the iockeys for a given name."""
        return self.map_name_to_iockeys[name]

    @synchronized()
    def watches_for_name(self, name):
        """Returns a list of all the watches for the given name."""
        watches = []
        for iockey in self.iokeys_for_name(name):
            watches.append(self.watch_for_iockey(iockey))
        return watches

    @synchronized()
    def watch_for_iockey(self, iockey):
        """Returns the watch object for the given iockey."""
        return self.map_iockey_to_watch[iockey]

    @property
    @synchronized()
    def watches(self):
        """A list of all the watches."""
        self.map_iockey_to_watches.values()


    @synchronized()
    def schedule(self, name, event_handler, paths, recursive=False):
        """Schedules monitoring specified paths and calls methods in the
        given callback handler based on events occurring in the file system.
        """
        if not paths:
            raise ValueError('Please specify a few paths.')
        if isinstance(paths, basestring):
            paths = [paths]

        self.map_name_to_iockeys[name] = set()
        for path in paths:
            if not isinstance(path, basestring):
                raise TypeError("Path must be string, not '%s'." % type(path).__name__)
            path = os.path.abspath(os.path.realpath(path)).rstrip(os.path.sep)
            iockey = self.iockey_counter
            watch = _Watch(iockey, name, event_handler, path, recursive)
            self.iockey_counter += 1
            self.map_iockey_to_watch[iockey] = watch
            self.map_name_to_iockeys[name].add(iockey)
            watch.associate_with_ioc_port(self.ioc_port)
            watch.read_directory_changes()

    @synchronized()
    def unschedule(self, *names):
        if not names:
            for watch in self.watches:
                watch.remove()
            self.map_iockey_to_watch = {}
            self.map_name_to_iockeys = {}
        else:
            for name in names:
                if name in self.map_name_to_iockeys:
                    for watch in self.watches_for_name(name):
                        watch.remove()
                        del self.map_iockey_to_watch[watch.iockey]
                        del self.map_name_to_iockeys[name]

    @synchronized()
    def remove_iockey(self, iockey):
        watch = self.watch_for_key(iockey)
        del self.map_iockey_to_watch[iockey]
        self.map_name_to_iockeys[watch.group_name].remove(iockey)
        watch.remove()

    @synchronized()
    def dispatch_events_for_iockey(self, iockey, num_bytes):
        watch = self.watch_for_iockey(iockey)
        if not watch.is_removed:
            watch.dispatch_events(num_bytes)
            watch.read_directory_changes()

    def run(self):
        while not self.is_stopped:
            # read status of io completion queue
            rc, num_bytes, iockey, _ = GetQueuedCompletionStatus(self.ioc_port, self.ioc_timeout)
            if rc == 0:
                # Successful.
                self.dispatch_events_for_iockey(iockey, num_bytes)
            elif rc == 5:
                # Error
                self.remove_iockey(self, iockey)

        # Clean up
        if self.ioc_port is not None:
            CloseHandle(self.ioc_port)
            self.ioc_port = None


