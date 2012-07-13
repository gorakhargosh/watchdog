#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from watchdog.utils import platform

if platform.is_windows():
  import ctypes

  from watchdog.observers.winapi import\
    FILE_FLAG_BACKUP_SEMANTICS,\
    FILE_FLAG_OVERLAPPED,\
    FILE_SHARE_READ,\
    FILE_SHARE_WRITE,\
    FILE_SHARE_DELETE,\
    FILE_NOTIFY_CHANGE_FILE_NAME,\
    FILE_NOTIFY_CHANGE_DIR_NAME,\
    FILE_NOTIFY_CHANGE_ATTRIBUTES,\
    FILE_NOTIFY_CHANGE_SIZE,\
    FILE_NOTIFY_CHANGE_LAST_WRITE,\
    FILE_NOTIFY_CHANGE_SECURITY,\
    FILE_NOTIFY_CHANGE_LAST_ACCESS,\
    FILE_NOTIFY_CHANGE_CREATION,\
    FILE_ACTION_CREATED,\
    FILE_ACTION_DELETED,\
    FILE_ACTION_MODIFIED,\
    FILE_LIST_DIRECTORY,\
    OPEN_EXISTING,\
    INVALID_HANDLE_VALUE,\
    CreateFileW,\
    ReadDirectoryChangesW,\
    CreateIoCompletionPort,\
    CancelIoEx
  from watchdog.events import\
    DirDeletedEvent,\
    DirCreatedEvent,\
    DirModifiedEvent,\
    FileDeletedEvent,\
    FileCreatedEvent,\
    FileModifiedEvent

  # We don't need to recalculate these flags every time a call is made to
  # the win32 API functions.
  WATCHDOG_FILE_FLAGS = FILE_FLAG_BACKUP_SEMANTICS
  WATCHDOG_FILE_FLAGS_ASYNC = FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED
  WATCHDOG_FILE_SHARE_FLAGS = reduce(lambda x, y: x | y, [
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    FILE_SHARE_DELETE,
    ])
  WATCHDOG_FILE_NOTIFY_FLAGS = reduce(lambda x, y: x | y, [
    FILE_NOTIFY_CHANGE_FILE_NAME,
    FILE_NOTIFY_CHANGE_DIR_NAME,
    FILE_NOTIFY_CHANGE_ATTRIBUTES,
    FILE_NOTIFY_CHANGE_SIZE,
    FILE_NOTIFY_CHANGE_LAST_WRITE,
    FILE_NOTIFY_CHANGE_SECURITY,
    FILE_NOTIFY_CHANGE_LAST_ACCESS,
    FILE_NOTIFY_CHANGE_CREATION,
    ])


  # HACK:
  WATCHDOG_TRAVERSE_MOVED_DIR_DELAY = 1   # seconds

  BUFFER_SIZE = 2048

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
    handle = CreateFileW(path,
                         FILE_LIST_DIRECTORY,
                         WATCHDOG_FILE_SHARE_FLAGS,
                         None,
                         OPEN_EXISTING,
                         file_flags,
                         None)
    return handle


  def close_directory_handle(handle):
    try:
      CancelIoEx(handle, None) #force ReadDirectoryChangesW to return
    except WindowsError:
      return


  def read_directory_changes(handle, event_buffer, recursive):
    """Read changes to the directory using the specified directory handle.

    http://timgolden.me.uk/pywin32-docs/win32file__ReadDirectoryChangesW_meth.html
    """
    nbytes = ctypes.wintypes.DWORD()
    try:
      ReadDirectoryChangesW(handle,
                            ctypes.byref(event_buffer),
                            len(event_buffer),
                            recursive,
                            WATCHDOG_FILE_NOTIFY_FLAGS,
                            ctypes.byref(nbytes),
                            None,
                            None)
    except WindowsError:
      return [], 0
    # get_FILE_NOTIFY_INFORMATION expects nBytes to be long.
    return event_buffer.raw, long(nbytes.value)


  def create_io_completion_port():
    """
    http://timgolden.me.uk/pywin32-docs/win32file__CreateIoCompletionPort_meth.html
    """
    return CreateIoCompletionPort(INVALID_HANDLE_VALUE, None, 0, 0)
