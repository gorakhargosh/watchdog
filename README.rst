Watchdog
========

|Build Status|

Python API and shell utilities to monitor file system events.

Works on 3.6+.

If you want to use Python 2.6, you should stick with watchdog < 0.10.0.

If you want to use Python 2.7, 3.4 or 3.5, you should stick with watchdog < 1.0.0.

Example API Usage
-----------------

A simple program that uses watchdog to monitor directories specified
as command-line arguments and logs events generated:

.. code-block:: python

    import sys
    import time
    import logging
    from watchdog.observers import Observer
    from watchdog.events import LoggingEventHandler

    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
        path = sys.argv[1] if len(sys.argv) > 1 else '.'
        event_handler = LoggingEventHandler()
        observer = Observer()
        observer.schedule(event_handler, path, recursive=True)
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
        --patterns="*.py;*.txt" \
        --ignore-directories \
        --recursive \
        .

You can use the ``shell-command`` subcommand to execute shell commands in
response to events:

.. code-block:: bash

    watchmedo shell-command \
        --patterns="*.py;*.txt" \
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
    $ python -m pip install -U watchdog[watchmedo]

Install from source:

.. code-block:: bash

    $ python -m pip install -e .

    # or to install the watchmedo utility:
    $ python -m pip install -e ".[watchmedo]"


Installation Caveats
~~~~~~~~~~~~~~~~~~~~

The ``watchmedo`` script depends on PyYAML_ which links with LibYAML_,
which brings a performance boost to the PyYAML parser. However, installing
LibYAML_ is optional but recommended. On Mac OS X, you can use homebrew_
to install LibYAML:

.. code-block:: bash

    $ brew install libyaml

On Linux, use your favorite package manager to install LibYAML. Here's how you
do it on Ubuntu:

.. code-block:: bash

    $ sudo apt install libyaml-dev

On Windows, please install PyYAML_ using the binaries they provide.

Documentation
-------------

You can browse the latest release documentation_ online.

Contribute
----------

Fork the `repository`_ on GitHub and send a pull request, or file an issue
ticket at the `issue tracker`_. For general help and questions use the official
`mailing list`_ or ask on `stackoverflow`_ with tag `python-watchdog`.

Create and activate your virtual environment, then::

    python -m pip install pytest pytest-cov
    python -m pip install -e ".[watchmedo]"
    python -m pytest tests

If you are making a substantial change, add an entry to the "Unreleased" section
of the `changelog`_.

Supported Platforms
-------------------

* Linux 2.6 (inotify)
* Mac OS X (FSEvents, kqueue)
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

1. Python 3.6 or above.
2. XCode_ (only on Mac OS X)
3. PyYAML_ (only for ``watchmedo`` script)
4. argh_ (only for ``watchmedo`` script)


Licensing
---------

Watchdog is licensed under the terms of the `Apache License, version 2.0`_.

Copyright 2011 `Yesudeep Mangalapilly`_.

Copyright 2012 Google, Inc & contributors.

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
* treewalker_
* `file.monitor`_
* pyfilesystem_

.. links:
.. _Yesudeep Mangalapilly: yesudeep@gmail.com
.. _source code: http://github.com/gorakhargosh/watchdog
.. _issue tracker: http://github.com/gorakhargosh/watchdog/issues
.. _Apache License, version 2.0: http://www.apache.org/licenses/LICENSE-2.0
.. _documentation: https://python-watchdog.readthedocs.io/
.. _stackoverflow: http://stackoverflow.com/questions/tagged/python-watchdog
.. _mailing list: http://groups.google.com/group/watchdog-python
.. _repository: http://github.com/gorakhargosh/watchdog
.. _issue tracker: http://github.com/gorakhargosh/watchdog/issues
.. _changelog: https://github.com/gorakhargosh/watchdog/blob/master/changelog.rst

.. _homebrew: http://mxcl.github.com/homebrew/
.. _argh: http://pypi.python.org/pypi/argh
.. _PyYAML: http://www.pyyaml.org/
.. _XCode: http://developer.apple.com/technologies/tools/xcode.html
.. _LibYAML: http://pyyaml.org/wiki/LibYAML

.. _pnotify: http://mark.heily.com/pnotify
.. _unison fsmonitor: https://webdav.seas.upenn.edu/viewvc/unison/trunk/src/fsmonitor.py?view=markup&pathrev=471
.. _fsmonitor: http://github.com/shaurz/fsmonitor
.. _guard: http://github.com/guard/guard
.. _pyinotify: http://github.com/seb-m/pyinotify
.. _inotify-tools: http://github.com/rvoicilas/inotify-tools
.. _jnotify: http://jnotify.sourceforge.net/
.. _treewalker: http://github.com/jbd/treewatcher
.. _file.monitor: http://github.com/pke/file.monitor
.. _pyfilesystem: http://code.google.com/p/pyfilesystem

.. |Build Status| image:: https://github.com/gorakhargosh/watchdog/workflows/Tests/badge.svg
   :target: https://github.com/gorakhargosh/watchdog/actions?query=workflow%3ATests
