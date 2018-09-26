.. :changelog:

API changes
-----------

`Unreleased <https://github.com/gorakhargosh/watchdog/compare/v0.9.0...master>`_ - yyyy-mm-dd
~~~~~

- Dropped support for Python 2.6, 3.2 and 3.3.
  If you are still running one of these obsolete Python version, you have to keep using Watchdog <= 0.9.0.
- Fixed several Python 3 warnings.
- Fixed a bug when calling ``FSEventsEmitter.stop()`` twice.
- Fixed missing field initializers  and unused parameters in ``watchdog_fsevents.c``.


`0.9.0 <https://github.com/gorakhargosh/watchdog/compare/v0.8.3...v0.9.0>`_ - 2018-08-28
~~~~~

- Fixed a bug in ``fsevents2.py`` when the ``path`` could be unproperly set.
- Fixed a crash when the root directory being watched by ``inotify`` was deleted.
- Fixed a possible ``DirDeletedEvent`` duplication on GNU/Linux when deleting a directory.
- Fixed the ``FILE_LIST_DIRECTORY`` constant in ``winapi.py``. 



`0.8.3 <https://github.com/gorakhargosh/watchdog/compare/v0.8.2...v0.8.3>`_ - 2015-02-11
~~~~~

- Refactored libc loading and improved error handling in ``inotify_c.py``.
- Fixed a possible unbound local error in ``inotify_c.py``.


0.8.2
~~~~~

- Event emitters are no longer started on schedule if ``Observer`` is not
  already running.


0.8.0
~~~~~

- ``DirectorySnapshot``: methods returning internal stat info replaced by
  ``mtime``, ``inode`` and ``path`` methods.
- ``DirectorySnapshot``: ``walker_callback`` parameter deprecated.
