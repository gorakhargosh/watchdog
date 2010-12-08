import sys
import time
from watchdog.tricks import LoggerTrick
from watchdog.observers import Observer

event_handler = LoggerTrick()
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

