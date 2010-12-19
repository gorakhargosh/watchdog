# -*- coding: utf-8 -*-
# winapi_async.py: Windows impl w/ ReadDirectoryChangesW + I/O Completion ports.
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

from __future__ import with_statement
from watchdog.utils import platform
from watchdog.events import FileDeletedEvent, FileModifiedEvent,\
    FileCreatedEvent, FileMovedEvent, DirDeletedEvent, DirModifiedEvent,\
    DirCreatedEvent, DirMovedEvent

if platform.is_windows():
    import threading
    import time

    from watchdog.observers.winapi_common import\
        read_directory_changes
    from watchdog.observers.api import\
        EventQueue,\
        EventEmitter,\
        BaseObserver,\
        DEFAULT_OBSERVER_TIMEOUT,\
        DEFAULT_EMITTER_TIMEOUT


    class WindowsApiAsyncEmitter(EventEmitter):
        """
        Platform-independent emitter that polls a directory to detect file
        system changes.
        """

        def __init__(self, event_queue, watch, timeout=DEFAULT_EMITTER_TIMEOUT):
            EventEmitter.__init__(self, event_queue, watch, timeout)
            self._lock = threading.Lock()

        def on_thread_exit(self):
            pass

        def queue_events(self, timeout):
            with self._lock:
                pass

    class WindowsApiAsyncObserver(BaseObserver):
        """
        Observer thread that schedules watching directories and dispatches
        calls to event handlers.
        """

        def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
            BaseObserver.__init__(self, emitter_class=WindowsApiAsyncEmitter,
                                  timeout=timeout)


