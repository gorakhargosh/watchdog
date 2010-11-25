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


from win32con import FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, \
    FILE_NOTIFY_CHANGE_FILE_NAME, FILE_NOTIFY_CHANGE_DIR_NAME, FILE_NOTIFY_CHANGE_ATTRIBUTES, \
    FILE_NOTIFY_CHANGE_SIZE, FILE_NOTIFY_CHANGE_LAST_WRITE, FILE_NOTIFY_CHANGE_SECURITY
from win32file import ReadDirectoryChangesW, CreateFile, CloseHandle

from os.path import realpath, abspath, sep as path_separator, join as path_join, isdir as path_isdir
from threading import Thread, Event as ThreadedEvent
from Queue import Queue

from watchdog.observers.polling_observer import PollingObserver, _Rule
from watchdog.events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent


# Windows API Constant for the CreateFile Windows API function.
FILE_LIST_DIRECTORY = 0x0001

# Event buffer size.
BUFFER_SIZE = 1024


# We don't need to recalculate these flags every time a call is made to
# the win32 API functions.
WATCHDOG_FILE_SHARE_FLAGS = FILE_SHARE_READ | FILE_SHARE_WRITE
WATCHDOG_FILE_NOTIFY_FLAGS = FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_DIR_NAME | \
    FILE_NOTIFY_CHANGE_ATTRIBUTES | FILE_NOTIFY_CHANGE_SIZE | \
    FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_SECURITY

# Constants defined by the Windows API.
FILE_ACTION_CREATED = 1
FILE_ACTION_DELETED = 2
FILE_ACTION_MODIFIED = 3
FILE_ACTION_RENAMED_OLD_NAME = 4
FILE_ACTION_RENAMED_NEW_NAME = 5

# Moved event is handled explicitly in the emitter thread.
DIR_ACTION_EVENT_MAP = {
    FILE_ACTION_CREATED: DirCreatedEvent,
    FILE_ACTION_DELETED: DirDeletedEvent,
    FILE_ACTION_MODIFIED: DirModifiedEvent,
}
FILE_ACTION_EVENT_MAP = {
    FILE_ACTION_CREATED: FileCreatedEvent,
    FILE_ACTION_DELETED: FileDeletedEvent,
    FILE_ACTION_MODIFIED: FileModifiedEvent,
}


def get_directory_handle(path):
    """Returns a Windows handle to the specified directory path."""
    handle = CreateFile(path,
                        FILE_LIST_DIRECTORY,
                        WATCHDOG_FILE_SHARE_FLAGS,
                        None,
                        OPEN_EXISTING,
                        FILE_FLAG_BACKUP_SEMANTICS,
                        None)
    return handle

def read_directory_changes(handle, recursive, buffer_size=BUFFER_SIZE):
    """Read changes to the directory using the specified directory handle."""
    results = ReadDirectoryChangesW(handle,
                                    buffer_size,
                                    recursive,
                                    WATCHDOG_FILE_NOTIFY_FLAGS,
                                    None,
                                    None)
    return results


class _Win32EventEmitter(Thread):
    """"""
    def __init__(self, path, out_event_queue, recursive, *args, **kwargs):
        Thread.__init__(self)
        self.stopped = ThreadedEvent()
        self.setDaemon(True)
        self.path = path
        self.out_event_queue = out_event_queue
        self.handle_directory = get_directory_handle(self.path)
        self.is_recursive = recursive

    def stop(self):
        self.stopped.set()

    def run(self):
        while not self.stopped.is_set():
            results = read_directory_changes(self.handle_directory, self.is_recursive)

            # TODO: Verify the assumption that the last renamed from event
            # points to a file which the next renamed to event matches.
            last_renamed_from_filename = ""
            q = self.out_event_queue
            for action, filename in results:
                filename = path_join(self.path, filename)
                if action == FILE_ACTION_RENAMED_OLD_NAME:
                    last_renamed_from_filename = filename
                elif action == FILE_ACTION_RENAMED_NEW_NAME:
                    if path_isdir(filename):
                        q.put((self.path, DirMovedEvent(last_renamed_from_filename, filename)))
                    else:
                        q.put((self.path, FileMovedEvent(last_renamed_from_filename, filename)))
                else:
                    if path_isdir(filename):
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

