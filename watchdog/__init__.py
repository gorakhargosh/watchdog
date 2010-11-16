# -*- coding: utf-8 -*-

import logging

logging.basicConfig(level=logging.DEBUG)

from events import FileSystemEventHandler

try:
    import _watchdog_fsevents
    logging.debug('Using FSEventsObserver.')
    from fsevents_observer import FSEventsObserver as Observer
except ImportError:
    logging.debug('Using PollingObserver as fallback.')
    from polling_observer import PollingObserver as Observer
