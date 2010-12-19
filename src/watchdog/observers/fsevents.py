# -*- coding: utf-8 -*-
# fsevents.py: FSEvents-based event emitter for Mac OS X.
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

"""
:module: watchdog.observers.fsevents
:synopsis: FSEvents based emitter implementation.
:author: Gora Khargosh <gora.khargosh@gmail.com>
:platforms: Mac OS X
"""

from __future__ import with_statement
from watchdog.utils import platform, absolute_path

if platform.is_darwin():
    import threading
    import os.path
    import _watchdog_fsevents as _fsevents

    from watchdog.observers.api import\
        BaseObserver,\
        EventEmitter,\
        DEFAULT_EMITTER_TIMEOUT,\
        DEFAULT_OBSERVER_TIMEOUT

    #import ctypes
    #from watchdog.observers.macapi import Constants
    #from watchdog.utils import ctypes_find_library

    #DEFAULT_CORE_FOUNDATION_PATH = \
    # '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
    #DEFAULT_CORE_SERVICES_PATH = \
    # '/System/Library/Frameworks/CoreServices.framework/CoreServices'

    #core_foundation = \
    #    ctypes.CDLL(ctypes_find_library('CoreFoundation',
    #                                    DEFAULT_CORE_FOUNDATION_PATH))
    #core_services = \
    #    ctypes.CDLL(ctypes_find_library('CoreServices',
    #                                    DEFAULT_CORE_SERVICES_PATH))

    class FSEventsEmitter(EventEmitter):
        """
        Mac OS X FSEvents Emitter class.

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
            self._lock = threading.Lock()

        def on_thread_exit(self):
            _fsevents.remove_watch(self.watch)
            _fsevents.stop(self)

        def run(self):
            try:
                def callback(paths, masks):
                    for path, mask in zip(paths, masks):
                        print(path, mask)

                # INFO: FSEvents reports directory notifications recursively
                # by default, so we do not need to add subdirectory paths.
                #pathnames = set([self.watch.path])
                #if self.watch.is_recursive:
                #    for root, directory_names, _ in os.walk(self.watch.path):
                #        for directory_name in directory_names:
                #            full_path = absolute_path(
                #                            os.path.join(root, directory_name))
                #            pathnames.add(full_path)

                pathnames = [self.watch.path]
                _fsevents.add_watch(self,
                                    self.watch,
                                    callback,
                                    pathnames)
                _fsevents.read_events(self)
            finally:
                self.on_thread_exit()


    class FSEventsObserver(BaseObserver):
        def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
            BaseObserver.__init__(self, emitter_class=FSEventsEmitter,
                                  timeout=timeout)
            print('foobar')
