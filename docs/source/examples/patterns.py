import sys
import time

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

import logging
logging.basicConfig(level=logging.DEBUG)

class MyEventHandler(PatternMatchingEventHandler):
    def on_any_event(self, event):
        logging.debug(event)

event_handler = MyEventHandler(patterns=['*.py', '*.pyc'],
                                ignore_patterns=['version.py'],
                                ignore_directories=True)
observer = Observer()
observer.schedule('a-unique-name', event_handler, sys.argv[1:], recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.unschedule('a-unique-name')
    observer.stop()
observer.join()

