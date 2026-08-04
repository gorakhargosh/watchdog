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
