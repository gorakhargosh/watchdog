.. include:: global.rst.inc

.. _examples:

Examples
========
This page showcases various complete, runnable examples demonstrating different features of the watchdog API.

Calling a Function for Every Event
----------------------------------
To send events to an existing function or bound method, define a small
:class:`watchdog.events.FileSystemEventHandler` subclass in your application.
The following example forwards events to a logging callback::

    python callable_event_handler.py /path/to/directory

.. literalinclude:: examples/callable_event_handler.py
   :language: python
   :linenos:

``CallableEventHandler`` is defined by this example, rather than imported from
Watchdog. Keep the handler instance if you need to pass it to
:meth:`~watchdog.observers.api.BaseObserver.remove_handler_for_watch` later.
The same instance also works with
:meth:`~watchdog.observers.api.BaseObserver.add_handler_for_watch`.

Callbacks run on the observer's dispatch thread. To hand events to another
thread for processing, use a queue's bound ``put`` method as the callback:

.. code-block:: python

    from queue import Queue

    from watchdog.events import FileSystemEvent

    events: Queue[FileSystemEvent] = Queue()
    event_handler = CallableEventHandler(events.put)
    observer = Observer()
    watch = observer.schedule(event_handler, ".", recursive=True)

Your consumer can then read events from ``events`` without doing its work on
the dispatch thread.

Pattern Matching Filter
-----------------------
To filter file system events using glob patterns (for example, only observing changes to ``.py`` or ``.pyc`` files), you can use the :class:`watchdog.events.PatternMatchingEventHandler`:

.. literalinclude:: examples/patterns.py
   :language: python
   :linenos:

Watch a Single File
-------------------
Observers watch directories, not individual files. To monitor one file, schedule its parent directory and filter events by the file name. The following example watches ``example.txt`` in the given directory; pass a different file name as the optional second argument::

    python single_file.py /path/to/directory [filename]

.. literalinclude:: examples/single_file.py
   :language: python
   :linenos:

Logging Trick
-------------
Watchdog also includes built-in "tricks" (pre-implemented event handlers). For instance, the :class:`watchdog.tricks.LoggerTrick` automatically logs events. Here is how you can use it:

.. literalinclude:: examples/logger.py
   :language: python
   :linenos:

Debouncing Events
-----------------
Text editors and build tools can emit several events for a single logical change. Use :class:`watchdog.utils.event_debouncer.EventDebouncer` to collect a burst of events and run an expensive action once the watched directory has been quiet for a short interval:

.. literalinclude:: examples/debounced.py
   :language: python
   :linenos:

Organizing Files by Type
------------------------
A common task is to keep a busy directory (such as a ``Downloads`` folder) tidy by automatically moving newly created files into category subfolders based on their file extension:

.. literalinclude:: examples/file_organizer.py
   :language: python
   :linenos:
