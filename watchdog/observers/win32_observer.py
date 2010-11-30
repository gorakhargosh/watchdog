# -*- coding: utf-8 -*-
# win32_observer.py: ReadDirectoryChangesW-based Win32 API observer for Windows.
#
# Copyright (C) 2009 Tim Golden <mail@timgolden.me.uk>
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

# Articles of interest:
# ---------------------
# Understanding ReadDirectoryChangesW - Part 1:
# http://qualapps.blogspot.com/2010/05/understanding-readdirectorychangesw.html
#
# Tim Golden's Implementation:
# http://timgolden.me.uk/python/win32_how_do_i/watch_directory_for_changes.html
#
# Notes:
# ------
# This implementation spawns an emitter worker thread that calls
# ReadDirectoryChangesW for each directory that needs to be monitored.
# Events are pooled into an event queue by each emitter worker thread.
# These events are consumed by an observer thread and dispatched to
# the appropriate specified event handler.


import time
import os.path
import threading

from watchdog.utils import DaemonThread
from watchdog.observers.w32_api import *
from watchdog.observers.polling_observer import PollingObserver


class _Win32EventEmitter(DaemonThread):
    """Win32 event emitter."""
    def __init__(self, path, out_event_queue, recursive, interval=1):
        super(_Win32EventEmitter, self).__init__(interval)
        
        self._lock = threading.Lock()
        
        self.path = path
        self._q = out_event_queue
        self._handle_directory = get_directory_handle(self.path, WATCHDOG_FILE_FLAGS)
        self._is_recursive = recursive


    def _read_events(self):
        with self._lock:
            results = read_directory_changes(self._handle_directory, self._is_recursive)

            # TODO: Verify the assumption that the last renamed from event
            # points to a file which the next renamed to event matches.
            last_renamed_from_src_path = ""
            for action, src_path in results:
                src_path = os.path.join(self.path, src_path)
                
                if action == FILE_ACTION_RENAMED_OLD_NAME:
                    last_renamed_from_src_path = src_path
                elif action == FILE_ACTION_RENAMED_NEW_NAME:
                    if os.path.isdir(src_path):
                        renamed_dir_path = absolute_path(last_renamed_from_src_path)
                        new_dir_path = absolute_path(src_path)

                        # Fire a moved event for the directory itself.
                        self._q.put((self.path, DirMovedEvent(renamed_dir_path, new_dir_path)))

                        # Fire moved events for all files within this
                        # directory if recursive.
                        if self._is_recursive:
                            # HACK: We introduce a forced delay before
                            # traversing the moved directory. This will read
                            # only file movement that finishes within this
                            # delay time.
                            time.sleep(WATCHDOG_DELAY_BEFORE_TRAVERSING_MOVED_DIRECTORY)
                            # TODO: The following may not execute because we need to wait for I/O to complete.
                            for moved_event in get_moved_events_for(renamed_dir_path, new_dir_path, recursive=True):
                                self._q.put((self.path, moved_event))
                    else:
                        self._q.put((self.path, FileMovedEvent(last_renamed_from_src_path, src_path)))
                else:
                    if os.path.isdir(src_path):
                        action_event_map = DIR_ACTION_EVENT_MAP
                    else:
                        action_event_map = FILE_ACTION_EVENT_MAP
                    self._q.put((self.path, action_event_map[action](src_path)))


    def run(self):
        while not self.is_stopped:
            self._read_events()
        # Close the handle once the thread completes.
        CloseHandle(self._handle_directory)


class Win32Observer(PollingObserver):
    """Windows API-based polling observer implementation."""
    def _create_event_emitter(self, path, recursive):
        return _Win32EventEmitter(path=path,
                                  out_event_queue=self.event_queue,
                                  recursive=recursive)

