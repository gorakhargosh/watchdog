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

4. Start the observer and wait for it to start generating events
   without blocking our main thread.

By default, an :class:`watchdog.observers.Observer` instance will not monitor
sub-directories. You can set ``recursive=True`` in the call to
:meth:`watchdog.observers.Observer.schedule` to ensure monitoring
entire directory trees.


A Simple Example
----------------

::

    import time
    import logging
    import watchdog

    logging.basicConfig(level=logging.DEBUG)

    observer = watchdog.observers.Observer()
    observer.schedule(name='a-unique-name',
                      event_handler=watchdog.events.LoggingEventHandler(),
                      paths=['.'],
                      recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.unschedule('a-unique-name')
        observer.stop()
    observer.join()

To stop the program, press Control-C.
