# -*- coding: utf-8 -*-
# Watchog - Python API to monitor file system events.
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com> and the Watchdog authors.
# MIT License.

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

