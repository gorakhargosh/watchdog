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
from watchdog.observers.w32_api import *
from watchdog.observers import DaemonThread
from watchdog.observers.polling_observer import PollingObserver


class _Win32EventEmitter(DaemonThread):
    """Win32 event emitter."""
    def __init__(self, path, out_event_queue, recursive, interval=1):
        super(_Win32EventEmitter, self).__init__(interval)
        self.path = path
        self.out_event_queue = out_event_queue
        self.handle_directory = get_directory_handle(self.path, WATCHDOG_FILE_FLAGS)
        self.is_recursive = recursive


    def run(self):
        while not self.is_stopped:
            results = read_directory_changes(self.handle_directory, self.is_recursive)

            # TODO: Verify the assumption that the last renamed from event
            # points to a file which the next renamed to event matches.
            last_renamed_from_filename = ""
            q = self.out_event_queue
            for action, filename in results:
                filename = os.path.join(self.path, filename)
                if action == FILE_ACTION_RENAMED_OLD_NAME:
                    last_renamed_from_filename = filename
                elif action == FILE_ACTION_RENAMED_NEW_NAME:
                    if os.path.isdir(filename):
                        renamed_dir_path = absolute_path(last_renamed_from_filename)
                        new_dir_path = absolute_path(filename)

                        # Fire a moved event for the directory itself.
                        q.put((self.path, DirMovedEvent(renamed_dir_path, new_dir_path)))

                        # Fire moved events for all files within this
                        # directory if recursive.
                        if self.is_recursive:
                            # HACK: We introduce a forced delay before
                            # traversing the moved directory. This will read
                            # only file movement that finishes within this
                            # delay time.
                            time.sleep(WATCHDOG_DELAY_BEFORE_TRAVERSING_MOVED_DIRECTORY)
                            # TODO: The following may not execute because we need to wait for I/O to complete.
                            for moved_event in get_moved_events_for(renamed_dir_path, new_dir_path, recursive=True):
                                q.put((self.path, moved_event))
                    else:
                        q.put((self.path, FileMovedEvent(last_renamed_from_filename, filename)))
                else:
                    if os.path.isdir(filename):
                        action_event_map = DIR_ACTION_EVENT_MAP
                    else:
                        action_event_map = FILE_ACTION_EVENT_MAP
                    q.put((self.path, action_event_map[action](filename)))

        # Close the handle once the thread completes.
        CloseHandle(self.handle_directory)


class Win32Observer(PollingObserver):
    """Windows API-based polling observer implementation."""
    def _create_event_emitter(self, path, recursive):
        return _Win32EventEmitter(path=path,
                                  out_event_queue=self.event_queue,
                                  recursive=recursive)

