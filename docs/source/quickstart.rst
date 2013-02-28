.. include:: global.rst.inc

.. _quickstart:

Quickstart
==========
Below we present a simple example that monitors the current directory
recursively (which means, it will traverse any sub-directories)
to detect changes. Here is what we will do with the API:

1. Create an instance of the :class:`watchdog.observers.Observer` thread class.

2. Implement a subclass of :class:`watchdog.events.FileSystemEventHandler`
   (or as in our case, we will use the built-in
   :class:`watchdog.events.LoggingEventHandler`, which already does).

3. Schedule monitoring a few paths with the observer instance
   attaching the event handler.

4. Start the observer thread and wait for it generate events
   without blocking our main thread.

By default, an :class:`watchdog.observers.Observer` instance will not monitor
sub-directories. By passing ``recursive=True`` in the call to
:meth:`watchdog.observers.Observer.schedule` monitoring
entire directory trees is ensured.


A Simple Example
----------------
The following example program will monitor the current directory recursively for
file system changes and simply log them to the console::

    import sys
    import time
    import logging
    from watchdog.observers import Observer
    from watchdog.events import LoggingEventHandler

    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
        path = sys.argv[1] if len(sys.argv) > 1 else '.'
        event_handler = LoggingEventHandler()
        observer = Observer()
        observer.schedule(event_handler, path, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

To stop the program, press Control-C.
