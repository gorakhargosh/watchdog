# coding: utf-8

import sys
import time

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer
from watchdog.observers.inotify_c import WATCHDOG_ALL_EVENTS

import logging
logging.basicConfig(level=logging.DEBUG)


class MyEventHandler(PatternMatchingEventHandler):
    def on_any_event(self, event):
        logging.debug(event)


event_handler = MyEventHandler(patterns=['*.py', '*.pyc'],
                               ignore_patterns=['version.py'],
                               ignore_directories=True)
observer = Observer()
observer.schedule(event_handler, sys.argv[1], recursive=True, event_mask=WATCHDOG_ALL_EVENTS)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
