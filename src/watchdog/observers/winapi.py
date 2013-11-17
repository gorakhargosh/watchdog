#!/usr/bin/env python
# -*- coding: utf-8 -*-
# winapi.py: Windows API-Python interface (removes dependency on pywin32)
#
# Copyright (C) 2007 Thomas Heller <theller@ctypes.org>
# Copyright (C) 2010 Will McGugan <will@willmcgugan.com>
# Copyright (C) 2010 Ryan Kelly <ryan@rfk.id.au>
# Copyright (C) 2010 Yesudeep Mangalapilly <yesudeep@gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and / or other materials provided with the distribution.
# * Neither the name of the organization nor the names of its contributors may
#   be used to endorse or promote products derived from this software without
#   specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Portions of this code were taken from pyfilesystem, which uses the above
# new BSD license.


from __future__ import with_statement
from watchdog.utils import platform


if not platform.is_windows():
    raise ImportError

import ctypes.wintypes
import struct

try:
    LPVOID = ctypes.wintypes.LPVOID
except AttributeError:
    # LPVOID wasn't defined in Py2.5, guess it was introduced in Py2.6
    LPVOID = ctypes.c_void_p

# Invalid handle value.
INVALID_HANDLE_VALUE = 0xFFFFFFFF     # -1

# File notification contants.
FILE_NOTIFY_CHANGE_FILE_NAME = 0x01
FILE_NOTIFY_CHANGE_DIR_NAME = 0x02
FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x04
FILE_NOTIFY_CHANGE_SIZE = 0x08
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x010
FILE_NOTIFY_CHANGE_LAST_ACCESS = 0x020
FILE_NOTIFY_CHANGE_CREATION = 0x040
FILE_NOTIFY_CHANGE_SECURITY = 0x0100

FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OVERLAPPED = 0x40000000
FILE_LIST_DIRECTORY = 0x01
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
FILE_SHARE_DELETE = 0x04
OPEN_EXISTING = 3

# File action constants.
FILE_ACTION_CREATED = 1
FILE_ACTION_DELETED = 2
FILE_ACTION_MODIFIED = 3
FILE_ACTION_RENAMED_OLD_NAME = 4
FILE_ACTION_RENAMED_NEW_NAME = 5
FILE_ACTION_OVERFLOW = 0xFFFF

# Aliases
FILE_ACTION_ADDED = FILE_ACTION_CREATED
FILE_ACTION_REMOVED = FILE_ACTION_DELETED

THREAD_TERMINATE = 0x0001

# IO waiting constants.
WAIT_ABANDONED = 0x00000080
WAIT_IO_COMPLETION = 0x000000C0
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


class OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal', LPVOID),
                ('InternalHigh', LPVOID),
                ('Offset', ctypes.wintypes.DWORD),
                ('OffsetHigh', ctypes.wintypes.DWORD),
                ('Pointer', LPVOID),
                ('hEvent', ctypes.wintypes.HANDLE),
                ]


def _errcheck_bool(value, func, args):
    if not value:
        raise ctypes.WinError()
    return args


def _errcheck_handle(value, func, args):
    if not value:
        raise ctypes.WinError()
    if value == INVALID_HANDLE_VALUE:
        raise ctypes.WinError()
    return args


def _errcheck_dword(value, func, args):
    if value == 0xFFFFFFFF:
        raise ctypes.WinError()
    return args

try:
    ReadDirectoryChangesW = ctypes.windll.kernel32.ReadDirectoryChangesW
except AttributeError:
    raise ImportError("ReadDirectoryChangesW is not available")

ReadDirectoryChangesW.restype = ctypes.wintypes.BOOL
ReadDirectoryChangesW.errcheck = _errcheck_bool
ReadDirectoryChangesW.argtypes = (
    ctypes.wintypes.HANDLE,  # hDirectory
    LPVOID,  # lpBuffer
    ctypes.wintypes.DWORD,  # nBufferLength
    ctypes.wintypes.BOOL,  # bWatchSubtree
    ctypes.wintypes.DWORD,  # dwNotifyFilter
    ctypes.POINTER(ctypes.wintypes.DWORD),  # lpBytesReturned
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
    LPVOID  # FileIOCompletionRoutine # lpCompletionRoutine
)

CreateFileW = ctypes.windll.kernel32.CreateFileW
CreateFileW.restype = ctypes.wintypes.HANDLE
CreateFileW.errcheck = _errcheck_handle
CreateFileW.argtypes = (
    ctypes.wintypes.LPCWSTR,  # lpFileName
    ctypes.wintypes.DWORD,  # dwDesiredAccess
    ctypes.wintypes.DWORD,  # dwShareMode
    LPVOID,  # lpSecurityAttributes
    ctypes.wintypes.DWORD,  # dwCreationDisposition
    ctypes.wintypes.DWORD,  # dwFlagsAndAttributes
    ctypes.wintypes.HANDLE  # hTemplateFile
)

CloseHandle = ctypes.windll.kernel32.CloseHandle
CloseHandle.restype = ctypes.wintypes.BOOL
CloseHandle.argtypes = (
    ctypes.wintypes.HANDLE,  # hObject
)

CancelIoEx = ctypes.windll.kernel32.CancelIoEx
CancelIoEx.restype = ctypes.wintypes.BOOL
CancelIoEx.errcheck = _errcheck_bool
CancelIoEx.argtypes = (
    ctypes.wintypes.HANDLE,  # hObject
    ctypes.POINTER(OVERLAPPED)  # lpOverlapped
)

CreateEvent = ctypes.windll.kernel32.CreateEventW
CreateEvent.restype = ctypes.wintypes.HANDLE
CreateEvent.errcheck = _errcheck_handle
CreateEvent.argtypes = (
    LPVOID,  # lpEventAttributes
    ctypes.wintypes.BOOL,  # bManualReset
    ctypes.wintypes.BOOL,  # bInitialState
    ctypes.wintypes.LPCWSTR,  # lpName
)

SetEvent = ctypes.windll.kernel32.SetEvent
SetEvent.restype = ctypes.wintypes.BOOL
SetEvent.errcheck = _errcheck_bool
SetEvent.argtypes = (
    ctypes.wintypes.HANDLE,  # hEvent
)

WaitForSingleObjectEx = ctypes.windll.kernel32.WaitForSingleObjectEx
WaitForSingleObjectEx.restype = ctypes.wintypes.DWORD
WaitForSingleObjectEx.errcheck = _errcheck_dword
WaitForSingleObjectEx.argtypes = (
    ctypes.wintypes.HANDLE,  # hObject
    ctypes.wintypes.DWORD,  # dwMilliseconds
    ctypes.wintypes.BOOL,  # bAlertable
)

CreateIoCompletionPort = ctypes.windll.kernel32.CreateIoCompletionPort
CreateIoCompletionPort.restype = ctypes.wintypes.HANDLE
CreateIoCompletionPort.errcheck = _errcheck_handle
CreateIoCompletionPort.argtypes = (
    ctypes.wintypes.HANDLE,  # FileHandle
    ctypes.wintypes.HANDLE,  # ExistingCompletionPort
    LPVOID,  # CompletionKey
    ctypes.wintypes.DWORD,  # NumberOfConcurrentThreads
)

GetQueuedCompletionStatus = ctypes.windll.kernel32.GetQueuedCompletionStatus
GetQueuedCompletionStatus.restype = ctypes.wintypes.BOOL
GetQueuedCompletionStatus.errcheck = _errcheck_bool
GetQueuedCompletionStatus.argtypes = (
    ctypes.wintypes.HANDLE,  # CompletionPort
    LPVOID,  # lpNumberOfBytesTransferred
    LPVOID,  # lpCompletionKey
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
    ctypes.wintypes.DWORD,  # dwMilliseconds
)

PostQueuedCompletionStatus = ctypes.windll.kernel32.PostQueuedCompletionStatus
PostQueuedCompletionStatus.restype = ctypes.wintypes.BOOL
PostQueuedCompletionStatus.errcheck = _errcheck_bool
PostQueuedCompletionStatus.argtypes = (
    ctypes.wintypes.HANDLE,  # CompletionPort
    ctypes.wintypes.DWORD,  # lpNumberOfBytesTransferred
    ctypes.wintypes.DWORD,  # lpCompletionKey
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
)


class FILE_NOTIFY_INFORMATION(ctypes.Structure):
    _fields_ = [("NextEntryOffset", ctypes.wintypes.DWORD),
                ("Action", ctypes.wintypes.DWORD),
                ("FileNameLength", ctypes.wintypes.DWORD),
                #("FileName", (ctypes.wintypes.WCHAR * 1))]
                ("FileName", (ctypes.c_char * 1))]

LPFNI = ctypes.POINTER(FILE_NOTIFY_INFORMATION)


def get_FILE_NOTIFY_INFORMATION(readBuffer, nBytes):
    results = []
    while nBytes > 0:
        fni = ctypes.cast(readBuffer, LPFNI)[0]
        ptr = ctypes.addressof(fni) + FILE_NOTIFY_INFORMATION.FileName.offset
        #filename = ctypes.wstring_at(ptr, fni.FileNameLength)
        filename = ctypes.string_at(ptr, fni.FileNameLength)
        results.append((fni.Action, filename.decode('utf-16')))
        numToSkip = fni.NextEntryOffset
        if numToSkip <= 0:
            break
        readBuffer = readBuffer[numToSkip:]
        nBytes -= numToSkip  # numToSkip is long. nBytes should be long too.
    return results


def get_FILE_NOTIFY_INFORMATION_alt(event_buffer, nBytes):
    """Extract the information out of a FILE_NOTIFY_INFORMATION structure."""
    pos = 0
    event_buffer = event_buffer[:nBytes]
    while pos < len(event_buffer):
        jump, action, namelen = struct.unpack("iii", event_buffer[pos:pos + 12])
        # TODO: this may return a shortname or a longname, with no way
        # to tell which.  Normalise them somehow?
        name = event_buffer[pos + 12:pos + 12 + namelen].decode("utf-16")
        yield (name, action)
        if not jump:
            break
        pos += jump
