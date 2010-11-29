import sys
import time
import watchdog
import watchdog.tricks

event_handler = watchdog.tricks.LoggerTrick()
observer = watchdog.Observer()
observer.schedule('a-unique-name', event_handler, sys.argv[1:], recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.unschedule('a-unique-name')
    observer.stop()
observer.join()

