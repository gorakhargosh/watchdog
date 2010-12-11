.. include:: global.rst.inc

.. _installation:

Installation
============
|project_name| requires Python 2.5 or above to work. If you are using a
Linux/FreeBSD/Mac OS X system, you already have Python installed. However,
you may wish to upgrade your system to Python 2.7 at least, because this
version comes with updates that can reduce compatibility
problems. See a list of :ref:`installation-dependencies`.

Installing from PyPI using pip
------------------------------

.. parsed-literal::

    $ pip install |project_name|

Installing from source tarballs
-------------------------------

.. parsed-literal::

    $ wget -c http://watchdog-python.googlecode.com/files/|project_name|-|project_version|.tar.gz
    $ tar zxvf |project_name|-|project_version|.tar.gz
    $ cd |project_name|-|project_version|
    $ python setup.py install

Installing from the code repository
-----------------------------------

.. parsed-literal::

    $ git clone git://github.com/gorakhargosh/|project_name|.git
    $ cd |project_name|
    $ python setup.py install

.. _installation-dependencies:

Dependencies
------------
|project_name| depends on many libraries to do its job. The following is
a list of dependencies you need based on the operating system you are
using.

+---------------------+-------------+-------------+-------------+-------------+
| Operating system    |   Windows   |  Linux 2.6  | Mac OS X/   |     BSD     |
| Dependency (row)    |             |             |   Darwin    |             |
+=====================+=============+=============+=============+=============+
| pywin32_            |     Yes     |             |             |             |
+---------------------+-------------+-------------+-------------+-------------+
| XCode_              |             |             |     Yes     |             |
+---------------------+-------------+-------------+-------------+-------------+
| pyyaml_             |     Yes     |     Yes     |     Yes     |     Yes     |
+---------------------+-------------+-------------+-------------+-------------+
| argh_               |     Yes     |     Yes     |     Yes     |     Yes     |
+---------------------+-------------+-------------+-------------+-------------+
| argparse_           |     Yes     |     Yes     |     Yes     |     Yes     |
+---------------------+-------------+-------------+-------------+-------------+
| select_backport_    |             |             |     Yes     |     Yes     |
| (Python 2.6/2.6)    |             |             |             |             |
+---------------------+-------------+-------------+-------------+-------------+
| a lot of luck       |     Yes     |             |             |             |
+---------------------+-------------+-------------+-------------+-------------+


Supported Platforms (and Caveats)
---------------------------------
|project_name| uses native APIs as much as possible falling back
to polling the disk periodically to compare directory snapshots
only when it cannot use an API natively-provided by the underlying
operating system. The following operating systems are currently
supported:

.. WARNING:: Differences between behaviors of these native API
             are noted below.


Linux 2.6+
    Linux kernel version 2.6 and later come with an API called inotify_
    that programs can use to monitor file system events. |project_name| can
    use this feature by relying on a third party library for python
    called PyInotify_. (Future releases may remove this dependency.)


Mac OS X
    The Darwin kernel/OS X API maintains two ways to monitor directories
    for file system events:

    * kqueue_
    * FSEvents_

    |project_name| can use whichever one is available, preferring
    FSEvents over ``kqueue(2)``. ``kqueue(2)`` uses open file descriptors for monitoring
    and the current implementation uses
    `Mac OS X File System Monitoring Performance Guidelines`_ to open
    these file descriptors only to monitor events, thus allowing
    OS X to unmount volumes that are being watched without locking them.

    .. NOTE:: More information about how |project_name| uses ``kqueue(2)`` is noted
              in `BSD Unix variants`_. Much of this information applies to
              Mac OS X as well.


_`BSD Unix variants`
    BSD variants come with kqueue_ which programs can use to monitor
    changes to open file descriptors. Because of the way ``kqueue(2)`` works,
    |project_name| needs to open these files and directories in read-only
    non-blocking mode and keep books about them.

    |project_name| will automatically open file descriptors for all
    new files/directories created and close those for which are deleted.

    .. NOTE:: The maximum number of open file descriptor per process limit
              on your operating system can hinder |project_name|'s ability to
              monitor files.

              You should ensure this limit is set to at least **1024**
              (or a value suitable to your usage). The following command
              appended to your ``~/.profile`` configuration file does
              this for you::

                  ulimit -n 1024


Windows XP and later
    The Windows API on Windows XP provides the ReadDirectoryChangesW_
    function, which operates in either synchronous or asynchronous mode.
    |project_name| contains implementations for both approaches.

    The asynchronous I/O implementation is more scalable, does not depend
    entirely only on Python threads, and is hence preferred over the
    synchronous blocking version, which |project_name| isolates from your main
    thread using Python threads so that your programs do not block.

    .. NOTE:: Since renaming is not the same operation as movement
              on Windows, |project_name| tries hard to convert renames to
              movement events. Also, because the ReadDirectoryChangesW_
              API function returns rename/movement events for directories
              even before the underlying I/O is complete, |project_name|
              may not be able to completely scan the moved directory
              in order to successfully queue movement events for
              files and directories within it.

OS Independent Polling
    |project_name| also includes a fallback-implementation that polls
    watched directories for changes by periodically comparing snapshots
    of the directory tree.

    .. NOTE:: Windows caveats again.

              Because Windows has no concept of ``inodes`` as Unix-y
              platforms do, there is no current reliable way of determining
              file/directory movement on Windows without help from the
              Windows API.

              You can use hashing for only those files in which you are
              interested in your event handlers to determine
              this, although it is rather slow. |project_name| does not
              attempt to handle this on Windows. It is left to your discretion.
