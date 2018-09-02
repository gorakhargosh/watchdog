.. :changelog:

API changes
-----------

`Unreleased <https://github.com/gorakhargosh/watchdog/compare/v0.9.0...master>`_ - yyyy-mm-dd
~~~~~


`0.9.0 <https://github.com/gorakhargosh/watchdog/compare/v0.8.3...v0.9.0>`_ - 2018-08-28
~~~~~

- ???


`0.8.3 <https://github.com/gorakhargosh/watchdog/compare/v0.8.2...v0.8.3>`_ - 2015-02-11
~~~~~

- ???


0.8.2
~~~~~

- Event emitters are no longer started on schedule if ``Observer`` is not
  already running.


0.8.0
~~~~~

- ``DirectorySnapshot``: methods returning internal stat info replaced by
  ``mtime``, ``inode`` and ``path`` methods.
- ``DirectorySnapshot``: ``walker_callback`` parameter deprecated.
