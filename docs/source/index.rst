.. watchdog documentation master file, created by
   sphinx-quickstart on Tue Nov 30 00:43:58 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. include:: global.rst.inc


Watchdog
========

Python API library and shell utilities to monitor file system events.

|project_name| is 2 things:

* Cross-platform Python API library for monitoring file system changes.
* Suite of shell utilities that monitor file system changes
  and execute other shell commands in response.

Example Usage
-------------

::
    
    import time
    import uuid
    import logging

    from watchdog.events import LoggingEventHandler
    from watchdog.observers import Observer
    
    logging.basicConfig(level=logging.DEBUG)
    
    identifier = uuid.uuid1().hex
    event_handler = LoggingEventHandler()
    
    observer = Observer()
    observer.schedule(identifier, event_handler, paths=['.'], recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.unschedule(identifier)
        observer.stop()
    observer.join()
    

Contents:

.. toctree::
   :maxdepth: 2

   introduction


Modules and API
===============

.. toctree::
   :maxdepth: 2

   modules/watchdog.events
   modules/watchdog.utils.collections
   modules/watchdog.observers.polling_observer


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

