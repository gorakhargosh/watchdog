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
