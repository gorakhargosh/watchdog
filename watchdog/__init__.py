# -*- coding: utf-8 -*-
# Watchog - Python API to monitor file system events.
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


import logging
from version import __version__, VERSION_INFO, VERSION_STRING
from events import FileSystemEventHandler

logging.basicConfig(level=logging.DEBUG)

try:
    import pyinotify
    logging.debug('Using InotifyObserver')
    from inotify_observer import InotifyObserver as Observer
except ImportError:
    try:
        import _watchdog_fsevents
        logging.debug('Using FSEventsObserver.')
        from fsevents_observer import FSEventsObserver as Observer
    except ImportError:
        try:
            import win32file
            import win32con
            logging.debug('Using Win32Observer.')
            from win32_observer import Win32Observer as Observer
        except ImportError:
            logging.debug('Using PollingObserver as fallback.')
            from polling_observer import PollingObserver as Observer

