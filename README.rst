Watchdog
========

|Build Status|
|CirrusCI Status|

Python API and shell utilities to monitor file system events.

Works on 3.9+.

Example API Usage
-----------------

A simple program that uses watchdog to monitor directories specified
as command-line arguments and logs events generated:

.. code-block:: python

    import time

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer


    class MyEventHandler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            print(event)


    event_handler = MyEventHandler()
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


Shell Utilities
---------------

Watchdog comes with an *optional* utility script called ``watchmedo``.
Please type ``watchmedo --help`` at the shell prompt to
know more about this tool.

Here is how you can log the current directory recursively
for events related only to ``*.py`` and ``*.txt`` files while
ignoring all directory events:

.. code-block:: bash

    watchmedo log \
        --patterns='*.py;*.txt' \
        --ignore-directories \
        --recursive \
        --verbose \
        .

You can use the ``shell-command`` subcommand to execute shell commands in
response to events:

.. code-block:: bash

    watchmedo shell-command \
        --patterns='*.py;*.txt' \
        --recursive \
        --command='echo "${watch_src_path}"' \
        .

Please see the help information for these commands by typing:

.. code-block:: bash

    watchmedo [command] --help


About ``watchmedo`` Tricks
~~~~~~~~~~~~~~~~~~~~~~~~~~

``watchmedo`` can read ``tricks.yaml`` files and execute tricks within them in
response to file system events. Tricks are actually event handlers that
subclass ``watchdog.tricks.Trick`` and are written by plugin authors. Trick
classes are augmented with a few additional features that regular event handlers
don't need.

An example ``tricks.yaml`` file:

.. code-block:: yaml

    tricks:
    - watchdog.tricks.LoggerTrick:
        patterns: ["*.py", "*.js"]
    - watchmedo_webtricks.GoogleClosureTrick:
        patterns: ['*.js']
        hash_names: true
        mappings_format: json                  # json|yaml|python
        mappings_module: app/javascript_mappings
        suffix: .min.js
        compilation_level: advanced            # simple|advanced
        source_directory: app/static/js/
        destination_directory: app/public/js/
        files:
          index-page:
          - app/static/js/vendor/jquery*.js
          - app/static/js/base.js
          - app/static/js/index-page.js
          about-page:
          - app/static/js/vendor/jquery*.js
          - app/static/js/base.js
          - app/static/js/about-page/**/*.js

The directory containing the ``tricks.yaml`` file will be monitored. Each trick
class is initialized with its corresponding keys in the ``tricks.yaml`` file as
arguments and events are fed to an instance of this class as they arrive.

Installation
------------
Install from PyPI using ``pip``:

.. code-block:: bash

    $ python -m pip install -U watchdog

    # or to install the watchmedo utility:
    $ python -m pip install -U "watchdog[watchmedo]"

Install from source:

.. code-block:: bash

    $ python -m pip install -e .

    # or to install the watchmedo utility:
    $ python -m pip install -e '.[watchmedo]'


Documentation
-------------

You can browse the latest release documentation_ online.

Contribute
----------

Fork the `repository`_ on GitHub and send a pull request, or file an issue
ticket at the `issue tracker`_. For general help and questions use
`stackoverflow`_ with tag `python-watchdog`.

Create and activate your virtual environment, then::

    python -m pip install tox
    python -m tox [-q] [-e ENV]

If you are making a substantial change, add an entry to the "Unreleased" section
of the `changelog`_.

Supported Platforms
-------------------

* Linux 2.6 (inotify)
* macOS (FSEvents, kqueue)
* FreeBSD/BSD (kqueue)
* Windows (ReadDirectoryChangesW with I/O completion ports;
  ReadDirectoryChangesW worker threads)
* OS-independent (polling the disk for directory snapshots and comparing them
  periodically; slow and not recommended)

Note that when using watchdog with kqueue, you need the
number of file descriptors allowed to be opened by programs
running on your system to be increased to more than the
number of files that you will be monitoring. The easiest way
to do that is to edit your ``~/.profile`` file and add
a line similar to::

    ulimit -n 1024

This is an inherent problem with kqueue because it uses
file descriptors to monitor files. That plus the enormous
amount of bookkeeping that watchdog needs to do in order
to monitor file descriptors just makes this a painful way
to monitor files and directories. In essence, kqueue is
not a very scalable way to monitor a deeply nested
directory of files and directories with a large number of
files.

About using watchdog with editors like Vim
------------------------------------------

Vim does not modify files unless directed to do so.
It creates backup files and then swaps them in to replace
the files you are editing on the disk. This means that
if you use Vim to edit your files, the on-modified events
for those files will not be triggered by watchdog.
You may need to configure Vim appropriately to disable
this feature.


About using watchdog with CIFS
------------------------------

When you want to watch changes in CIFS, you need to explicitly tell watchdog to
use ``PollingObserver``, that is, instead of letting watchdog decide an
appropriate observer like in the example above, do::

    from watchdog.observers.polling import PollingObserver as Observer


Dependencies
------------

1. Python 3.9 or above.
2. XCode_ (only on macOS when installing from sources)
3. PyYAML_ (only for ``watchmedo``)

Licensing
---------

Watchdog is licensed under the terms of the `Apache License, version 2.0`_.

- Copyright 2018-2024 Mickaël Schoentgen & contributors
- Copyright 2014-2018 Thomas Amland & contributors
- Copyright 2012-2014 Google, Inc.
- Copyright 2011-2012 Yesudeep Mangalapilly

Project `source code`_ is available at Github. Please report bugs and file
enhancement requests at the `issue tracker`_.

Why Watchdog?
-------------

Too many people tried to do the same thing and none did what I needed Python
to do:

* pnotify_
* `unison fsmonitor`_
* fsmonitor_
* guard_
* pyinotify_
* `inotify-tools`_
* jnotify_
* treewatcher_
* `file.monitor`_
* pyfilesystem_

.. links:
.. _Yesudeep Mangalapilly: yesudeep@gmail.com
.. _source code: https://github.com/gorakhargosh/watchdog
.. _issue tracker: https://github.com/gorakhargosh/watchdog/issues
.. _Apache License, version 2.0: https://www.apache.org/licenses/LICENSE-2.0
.. _documentation: https://python-watchdog.readthedocs.io/
.. _stackoverflow: https://stackoverflow.com/questions/tagged/python-watchdog
.. _repository: https://github.com/gorakhargosh/watchdog
.. _issue tracker: https://github.com/gorakhargosh/watchdog/issues
.. _changelog: https://github.com/gorakhargosh/watchdog/blob/master/changelog.rst

.. _PyYAML: https://www.pyyaml.org/
.. _XCode: https://developer.apple.com/technologies/tools/xcode.html

.. _pnotify: http://mark.heily.com/pnotify
.. _unison fsmonitor: https://webdav.seas.upenn.edu/viewvc/unison/trunk/src/fsmonitor.py?view=markup&pathrev=471
.. _fsmonitor: https://github.com/shaurz/fsmonitor
.. _guard: https://github.com/guard/guard
.. _pyinotify: https://github.com/seb-m/pyinotify
.. _inotify-tools: https://github.com/rvoicilas/inotify-tools
.. _jnotify: http://jnotify.sourceforge.net/
.. _treewatcher: https://github.com/jbd/treewatcher
.. _file.monitor: https://github.com/pke/file.monitor
.. _pyfilesystem: https://github.com/PyFilesystem/pyfilesystem

.. |Build Status| image:: https://github.com/gorakhargosh/watchdog/workflows/Tests/badge.svg
   :target: https://github.com/gorakhargosh/watchdog/actions?query=workflow%3ATests
.. |CirrusCI Status| image:: https://api.cirrus-ci.com/github/gorakhargosh/watchdog.svg
   :target: https://cirrus-ci.com/github/gorakhargosh/watchdog/
