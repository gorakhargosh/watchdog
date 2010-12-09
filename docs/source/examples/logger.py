#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import time

from watchdog.observers import Observer
from watchdog.tricks import LoggerTrick

event_handler = LoggerTrick()
observer = Observer()
observer.schedule(event_handler, sys.argv[1], recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()

