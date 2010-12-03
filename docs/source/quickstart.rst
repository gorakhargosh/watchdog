.. include:: global.rst.inc

Quickstart
==========
.. contents::

|project_name| is 2 things:

* Cross-platform Python API library for monitoring file system changes.
* Suite of shell utilities that monitor file system changes
  and execute other shell commands in response.
 
Example using the library
--------------------------

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
 