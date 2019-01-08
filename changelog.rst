.. :changelog:

API changes
-----------

0.10.0
~~~~~~

- Dropped support for Python 2.6, 3.2 and 3.3.
  If you are still running one of these obsolete Python version, you have to keep using watchdog < 0.10.0.
- The ``watchmedo`` utility is no more installed by default but via the extra ``watchdog[watchmedo]``.

0.8.2
~~~~~

- Event emitters are no longer started on schedule if ``Observer`` is not
  already running.


0.8.0
~~~~~

- ``DirectorySnapshot``: methods returning internal stat info replaced by
  ``mtime``, ``inode`` and ``path`` methods.
- ``DirectorySnapshot``: ``walker_callback`` parameter deprecated.
