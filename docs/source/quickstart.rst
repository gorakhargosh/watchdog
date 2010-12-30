.. include:: global.rst.inc

.. _quickstart:

Quickstart
==========
Below we present a simple example that monitors the current directory
non-recursively (which means, it will not traverse any sub-directories)
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
sub-directories. You can set ``recursive=True`` in the call to
:meth:`watchdog.observers.Observer.schedule` to ensure monitoring
entire directory trees.


A Simple Example
----------------
The following example program will monitor the current directory recursively for
file system changes and simply log them to the console::

    import time
    from watchdog.observers import Observer
    from watchdog.events import LoggingEventHandler

    if __name__ == "__main__":
        event_handler = LoggingEventHandler()
        observer = Observer()
        observer.schedule(event_handler, path='.', recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

To stop the program, press Control-C.
