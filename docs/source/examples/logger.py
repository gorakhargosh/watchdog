# coding: utf-8

import sys
import time

from watchdog.observers import Observer
from watchdog.tricks import LoggerTrick
from watchdog.observers.inotify_c import WATCHDOG_ALL_EVENTS

event_handler = LoggerTrick()
observer = Observer()
observer.schedule(event_handler, sys.argv[1], recursive=True, event_mask=WATCHDOG_ALL_EVENTS)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
