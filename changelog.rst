.. :changelog:

API changes
-----------


0.8.1 - unreleased
~~~~~~~~~~~~~~~~~~

- ``EventEmitter.start()`` no waits for emitter to start.
- Don't start the emitter unless the main observer is not started.


0.8.0
~~~~~

 - ``DirectorySnapshot``: methods returning internal stat info replaced by
   ``mtime``, ``inode`` and ``path`` methods.
 - ``DirectorySnapshot``: ``walker_callback`` parameter deprecated.
