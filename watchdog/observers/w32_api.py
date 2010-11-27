# -*- coding: utf-8 -*-
# w32_api.py: Common routines and constants for the Win32 API used.
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

from win32con import FILE_SHARE_READ, \
    FILE_SHARE_WRITE, \
    FILE_SHARE_DELETE, \
    OPEN_EXISTING, \
    FILE_FLAG_BACKUP_SEMANTICS, \
    FILE_FLAG_OVERLAPPED, \
    FILE_NOTIFY_CHANGE_FILE_NAME, \
    FILE_NOTIFY_CHANGE_DIR_NAME, \
    FILE_NOTIFY_CHANGE_ATTRIBUTES, \
    FILE_NOTIFY_CHANGE_SIZE, \
    FILE_NOTIFY_CHANGE_LAST_WRITE, \
    FILE_NOTIFY_CHANGE_SECURITY

from win32file import ReadDirectoryChangesW, \
    CreateFile, \
    CloseHandle, \
    CancelIo, \
    CreateIoCompletionPort, \
    GetQueuedCompletionStatus, \
    FILE_NOTIFY_INFORMATION

from watchdog.events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent


# Windows API Constants.
FILE_LIST_DIRECTORY = 0x0001            # CreateFile
INVALID_HANDLE_VALUE = -1               # CreateIoCompletionPort to create an unassociated i/o completion port.
FILE_NOTIFY_CHANGE_LAST_ACCESS = 0x20   # ReadDirectoryChangesW
FILE_NOTIFY_CHANGE_CREATION = 0x40      # ReadDirectoryChangesW

# Event buffer size.
BUFFER_SIZE = 1024

# File action constants defined by the Windows API.
FILE_ACTION_CREATED = 1
FILE_ACTION_DELETED = 2
FILE_ACTION_MODIFIED = 3
FILE_ACTION_RENAMED_OLD_NAME = 4
FILE_ACTION_RENAMED_NEW_NAME = 5

# We don't need to recalculate these flags every time a call is made to
# the win32 API functions.
WATCHDOG_FILE_FLAGS = FILE_FLAG_BACKUP_SEMANTICS
WATCHDOG_FILE_FLAGS_ASYNC = FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED
WATCHDOG_FILE_SHARE_FLAGS = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
WATCHDOG_FILE_NOTIFY_FLAGS = FILE_NOTIFY_CHANGE_FILE_NAME | \
    FILE_NOTIFY_CHANGE_DIR_NAME | \
    FILE_NOTIFY_CHANGE_ATTRIBUTES | \
    FILE_NOTIFY_CHANGE_SIZE | \
    FILE_NOTIFY_CHANGE_LAST_WRITE | \
    FILE_NOTIFY_CHANGE_SECURITY | \
    FILE_NOTIFY_CHANGE_LAST_ACCESS | \
    FILE_NOTIFY_CHANGE_CREATION

# HACK:
WATCHDOG_DELAY_BEFORE_TRAVERSING_MOVED_DIRECTORY = 2   # seconds


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


def get_directory_handle(path, file_flags):
    """Returns a Windows handle to the specified directory path."""
    handle = CreateFile(path,
                        FILE_LIST_DIRECTORY,
                        WATCHDOG_FILE_SHARE_FLAGS,
                        None,
                        OPEN_EXISTING,
                        file_flags,
                        None)
    return handle


def read_directory_changes(handle, recursive, buffer_size=BUFFER_SIZE):
    """Read changes to the directory using the specified directory handle.

    http://timgolden.me.uk/pywin32-docs/win32file__ReadDirectoryChangesW_meth.html
    """
    results = ReadDirectoryChangesW(handle,
                                    buffer_size,
                                    recursive,
                                    WATCHDOG_FILE_NOTIFY_FLAGS,
                                    None,
                                    None)
    return results


def create_io_completion_port():
    """
    http://timgolden.me.uk/pywin32-docs/win32file__CreateIoCompletionPort_meth.html
    """
    return CreateIoCompletionPort(INVALID_HANDLE_VALUE, None, 0, 0)
