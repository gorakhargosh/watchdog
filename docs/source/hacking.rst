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
3. XCode_ (on macOS)

Setting up the Work Environment
-------------------------------

Steps to setting up a clean environment:

1. Fork the `code repository`_ into your github_ account.

2. Clone fork and create virtual environment:

.. code:: bash

    $ git clone https://github.com/gorakhargosh/watchdog.git
    $ cd watchdog
    $ python -m venv venv

3. Linux

.. code:: bash

    $ . venv/bin/activate
    (venv)$ python -m pip instal -e '.'

4. Windows

.. code:: batch

    > venv\Scripts\activate
    (venv)> python -m pip instal -e '.'

That's it with the setup. Now you're ready to hack on |project_name|.

Happy hacking!
