.. include:: global.rst.inc

.. _examples:

Examples
========
This page showcases various complete, runnable examples demonstrating different features of the watchdog API.

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

Pre-check / Validated Auto-Restart
----------------------------------
During development, check source files before replacing a running worker. This example watches Python files recursively and uses :mod:`py_compile` to check every ``.py`` file before the initial start and each restart. If validation fails, it logs the reason and leaves the current worker running. Fixing the source triggers another check.

Pass a source directory and an optional command, which runs in that directory::

    python validated_restart.py /path/to/source python worker.py

For direct commands of the form ``python worker.py [args ...]``, the example also checks that the entry-point file exists before stopping the current worker. If it is missing, the example logs a warning and keeps the worker running until the file is restored.

With only a directory argument, the example starts a built-in demo worker. Keep virtual environments outside the watched source tree. The check validates syntax only; it does not verify imports or runtime behavior. Press Ctrl+C to stop the observer and worker.

.. literalinclude:: examples/validated_restart.py
   :language: python
   :linenos:
