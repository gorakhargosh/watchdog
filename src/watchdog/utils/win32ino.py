# -*- coding: utf-8 -*-
#
# Copyright 2014 Thomas Amland <thomas.amland@gmail.com>
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

"""
:module: watchdog.utils.win32ino
:synopsis: Inode-like unique file IDs for Windows. Implementation is similar
to that of `os.stat` in python 3.

Functions
---------

.. autofunction:: file_id

"""

import ctypes
import ctypes.wintypes


INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
OPEN_EXISTING = 3
FILE_READ_ATTRIBUTES = 0x80
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.wintypes.DWORD),
                ("dwHighDateTime", ctypes.wintypes.DWORD)]


class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [('dwFileAttributes', ctypes.wintypes.DWORD),
                ('ftCreationTime', FILETIME),
                ('ftLastAccessTime', FILETIME),
                ('ftLastWriteTime', FILETIME),
                ('dwVolumeSerialNumber', ctypes.wintypes.DWORD),
                ('nFileSizeHigh', ctypes.wintypes.DWORD),
                ('nFileSizeLow', ctypes.wintypes.DWORD),
                ('nNumberOfLinks', ctypes.wintypes.DWORD),
                ('nFileIndexHigh', ctypes.wintypes.DWORD),
                ('nFileIndexLow', ctypes.wintypes.DWORD)]


CreateFile = ctypes.windll.kernel32.CreateFileW
CreateFile.restype = ctypes.wintypes.HANDLE
CreateFile.argtypes = (
    ctypes.c_wchar_p,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.HANDLE,
)

GetFileInformationByHandle = ctypes.windll.kernel32.GetFileInformationByHandle
GetFileInformationByHandle.restype = ctypes.wintypes.BOOL
GetFileInformationByHandle.argtypes = (
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.POINTER(BY_HANDLE_FILE_INFORMATION),
)

CloseHandle = ctypes.windll.kernel32.CloseHandle
CloseHandle.restype = ctypes.wintypes.BOOL
CloseHandle.argtypes = (ctypes.wintypes.HANDLE,)


def file_id(path):
    hfile = CreateFile(path,
            FILE_READ_ATTRIBUTES,
            0,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            None)
    if hfile == INVALID_HANDLE_VALUE:
        raise ctypes.WinError()
    info = BY_HANDLE_FILE_INFORMATION()
    r = GetFileInformationByHandle(hfile, info)
    CloseHandle(hfile)
    if not r:
        raise ctypes.WinError()
    return (info.nFileIndexHigh << 32) + info.nFileIndexLow
