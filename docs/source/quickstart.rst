.. include:: global.rst.inc

.. _quickstart:

Quickstart
==========
Below we present a simple example that monitors the current directory
recursively (which means, it will traverse any sub-directories)
to detect changes. Here is what we will do with the API:

1. Create an instance of the :class:`watchdog.observers.Observer` thread class.

2. Implement a subclass of :class:`watchdog.events.FileSystemEventHandler`.

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
file system changes and simply print them to the console::

    import time

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer


    class MyEventHandler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            print(event)


    event_handler = MyEventHandler()
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()

To stop the program, press Control-C.
