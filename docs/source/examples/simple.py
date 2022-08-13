# coding: utf-8

import logging
import sys
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.inotify_c import WATCHDOG_ALL_EVENTS

logging.basicConfig(level=logging.DEBUG)


class MyEventHandler(FileSystemEventHandler):
    def catch_all_handler(self, event):
        logging.debug(event)

    def on_moved(self, event):
        self.catch_all_handler(event)

    def on_created(self, event):
        self.catch_all_handler(event)

    def on_deleted(self, event):
        self.catch_all_handler(event)

    def on_modified(self, event):
        self.catch_all_handler(event)


path = sys.argv[1]

event_handler = MyEventHandler()
observer = Observer()
observer.schedule(event_handler, path, recursive=True, event_mask=WATCHDOG_ALL_EVENTS)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
