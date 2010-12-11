# -*- coding: utf-8 -*-
# inotify.py: inotify-based event emitter for Linux 2.6.13+.
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

"""
:module: watchdog.observers.inotify
:synopsis: ``inotify(7)`` based emitter implementation.
:author: Luke McCarthy <luke@iogopro.co.uk>
:author: Gora Khargosh <gora.khargosh@gmail.com>
:platforms: Linux 2.6.13+.

.. ADMONITION:: About system requirements

    Recommended minimum kernel version: 2.6.25.

    Quote from the inotify(7) man page:

        "Inotify was merged into the 2.6.13 Linux kernel. The required library
        interfaces were added to glibc in version 2.4. (IN_DONT_FOLLOW,
        IN_MASK_ADD, and IN_ONLYDIR were only added in version 2.5.)"

    Therefore, you must ensure the system is running at least these versions
    appropriate libraries and the kernel.

.. ADMONITION:: About recursiveness, event order, and event coalescing

    Quote from the inotify(7) man page:

        If successive output inotify events produced on the inotify file
        descriptor are identical (same wd, mask, cookie, and name) then they
        are coalesced into a single event if the older event has not yet been
        read (but see BUGS).

        The events returned by reading from an inotify file descriptor form
        an ordered queue. Thus, for example, it is guaranteed that when
        renaming from one directory to another, events will be produced in
        the correct order on the inotify file descriptor.

        ...

        Inotify monitoring of directories is not recursive: to monitor
        subdirectories under a directory, additional watches must be created.

    This emitter implementation therefore automatically adds watches for
    sub-directories if running in recursive mode.
"""

from __future__ import with_statement
from watchdog.utils import platform

if platform.is_linux():
    import os
    import struct
    import threading

    from ctypes import \
        CDLL, \
        CFUNCTYPE, \
        POINTER, \
        c_int, \
        c_char_p, \
        c_uint32, \
        get_errno
    from watchdog.observers.api import \
        EventEmitter, \
        BaseObserver, \
        DEFAULT_EMITTER_TIMEOUT, \
        DEFAULT_OBSERVER_TIMEOUT

    libc = CDLL('libc.so.6')

    strerror = CFUNCTYPE(c_char_p, c_int)(
        ("strerror", libc))
    inotify_init = CFUNCTYPE(c_int, use_errno=True)(
        ("inotify_init", libc))
    inotify_add_watch = \
        CFUNCTYPE(c_int, c_int, c_char_p, c_uint32, use_errno=True)(
            ("inotify_add_watch", libc))
    inotify_rm_watch = CFUNCTYPE(c_int, c_int, c_int, use_errno=True)(
        ("inotify_rm_watch", libc))

    # Supported events suitable for MASK parameter of ``inotify_add_watch``
    IN_ACCESS        = 0x00000001     # File was accessed.
    IN_MODIFY        = 0x00000002     # File was modified.
    IN_ATTRIB        = 0x00000004     # Meta-data changed.
    IN_CLOSE_WRITE   = 0x00000008     # Writable file was closed.
    IN_CLOSE_NOWRITE = 0x00000010     # Unwritable file closed.
    IN_CLOSE         = IN_CLOSE_WRITE | IN_CLOSE_NOWRITE  # Close.
    IN_OPEN          = 0x00000020     # File was opened.
    IN_MOVED_FROM    = 0x00000040     # File was moved from X.
    IN_MOVED_TO      = 0x00000080     # File was moved to Y.
    IN_MOVE          = IN_MOVED_FROM | IN_MOVED_TO  # Moves.
    IN_CREATE        = 0x00000100     # Subfile was created.
    IN_DELETE        = 0x00000200     # Subfile was deleted.
    IN_DELETE_SELF   = 0x00000400     # Self was deleted.
    IN_MOVE_SELF     = 0x00000800     # Self was moved.

    # Events sent by the kernel.
    IN_UNMOUNT       = 0x00002000     # Backing file system was unmounted.
    IN_Q_OVERFLOW    = 0x00004000     # Event queued overflowed.
    IN_IGNORED       = 0x00008000     # File was ignored.

    # Special flags.
    IN_ONLYDIR       = 0x01000000     # Only watch the path if it's a directory.
    IN_DONT_FOLLOW   = 0x02000000     # Do not follow a symbolic link.
    IN_MASK_ADD      = 0x20000000     # Add to the mask of an existing watch.
    IN_ISDIR         = 0x40000000     # Event occurred against directory.
    IN_ONESHOT       = 0x80000000     # Only send event once.

    MASK_MONITORING_EVENTS = reduce(lambda x, y: x | y, [
        IN_ACCESS,
        IN_MODIFY,
        IN_ATTRIB,
        IN_CLOSE_WRITE,
        IN_CLOSE_NOWRITE,
        IN_OPEN,
        IN_MOVED_FROM,
        IN_MOVED_TO,
        IN_CREATE,
        IN_DELETE,
        IN_DELETE_SELF,
        IN_MOVE_SELF,
    ])
    print(MASK_MONITORING_EVENTS)


    class InotifyEmitter(EventEmitter):
        """
        inotify(7)-based event emitter.

        :param event_queue:
            The event queue to fill with events.
        :param watch:
            A watch object representing the directory to monitor.
        :type watch:
            :class:`watchdog.observers.api.ObservedWatch`
        :param timeout:
            Read events blocking timeout (in seconds).
        :type timeout:
            ``float``
        """
        def __init__(self, event_queue, watch, timeout=DEFAULT_EMITTER_TIMEOUT):
            EventEmitter.__init__(self, event_queue, watch, timeout)


        def on_thread_exit(self):
            pass


        def _parse_events(self, buffer):
            """
            Parses and event buffer of ``inotify_event`` structs returned by
            reading for events using inotify.
            """
            i = 0
            while i + 16 < len(buffer):
                wd, mask, cookie, length = struct.unpack_from('iIII', buffer, i)
                name = buffer[i + 16:i + 16 + length].rstrip('\0')
                i += 16 + length
                yield wd, mask, cookie, name


        def queue_events(self, timeout):
            pass


    class InotifyObserver(BaseObserver):
        """
        Observer thread that schedules watching directories and dispatches
        calls to event handlers.
        """
        def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
            BaseObserver.__init__(self, emitter_class=InotifyEmitter, timeout=timeout)
