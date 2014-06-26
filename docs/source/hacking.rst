.. include:: global.rst.inc

.. _hacking:

Contributing
============
Welcome hacker! So you have got something you would like to see in
|project_name|? Whee. This document will help you get started.

Important URLs
--------------
|project_name| uses git_ to track code history and hosts its `code repository`_
at github_. The `issue tracker`_ is where you can file bug reports and request
features or enhancements to |project_name|.

Before you start
----------------
Ensure your system has the following programs and libraries installed before
beginning to hack:

1. Python_
2. git_
3. ssh
4. XCode_ (on Mac OS X)
5. select_backport_ (on BSD/Mac OS X if you're using Python 2.6)

Setting up the Work Environment
-------------------------------
|project_name| makes extensive use of zc.buildout_ to set up its work
environment. You should get familiar with it.


Steps to setting up a clean environment:

1. Fork the `code repository`_ into your github_ account. Let us call you
   ``hackeratti`` for the sake of this example. Replace ``hackeratti``
   with your own username below.

2. Clone your fork and setup your environment::

    $ git clone --recursive git@github.com:hackeratti/watchdog.git
    $ cd watchdog
    $ python tools/bootstrap.py --distribute
    $ bin/buildout

.. IMPORTANT:: Re-run ``bin/buildout`` every time you make a change to the
               ``buildout.cfg`` file.

That's it with the setup. Now you're ready to hack on |project_name|.

Enabling Continuous Integration
-------------------------------
The repository checkout contains a script called ``autobuild.sh``
which you must run prior to making changes. It will detect changes to
Python source code or restructuredText documentation files anywhere
in the directory tree and rebuild sphinx_ documentation, run all tests using
nose_, and generate coverage_ reports.

Start it by issuing this command in the ``watchdog`` directory
checked out earlier::

    $ tools/autobuild.sh
    ...

Happy hacking!
