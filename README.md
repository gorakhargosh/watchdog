Watchdog
========
Python API to monitor file system events.

Example Usage:
--------------

<pre>import sys
import time
from watchdog import Observer
from watchdog.events import FileSystemEventHandler
import logging

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


event_handler = MyEventHandler()
observer = Observer()
observer.schedule('a-unique-name', event_handler, recursive=True, sys.argv[1:])
observer.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.unschedule('a-unique-name')
    observer.stop()
observer.join()</pre>


Introduction:
-------------
Watchdog lets your Python programs monitor filesystem events as
portably as possible using:

* inotify on Linux
* FSEvents on Mac OS X
* Windows API on Windows.
* polling as a fallback mechanism

Dependencies:
-------------
1. [pywin32](http://sourceforge.net/projects/pywin32/) (only on Windows)
2. [pyinotify](http://github.com/seb-m/pyinotify) (only on Linux)
3. XCode or gcc (only on Mac OS X)
4. [PyYAML](http://www.pyyaml.org/)
5. [argh](http://pypi.python.org/pypi/argh)

Licensing:
----------
Watchdog is licensed under the terms of the
[MIT License](http://www.opensource.org/licenses/mit-license.html)

Copyright (C) 2010 Gora Khargosh &lt;gora.khargosh@gmail.com&gt; and the Watchdog authors.

Project source code on [Github](http://github.com/gorakhargosh/watchdog)

