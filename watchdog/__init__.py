# -*- coding: utf-8 -*-

from events import FileSystemEventHandler

try:
    import _fsevents
    from fsevents_observer import FSEventsObserver as Observer
except ImportError:
    from polling_observer import PollingObserver as Observer

