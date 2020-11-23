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
3. XCode_ (on Mac OS X)

Setting up the Work Environment
-------------------------------

Steps to setting up a clean environment:

1. Fork the `code repository`_ into your github_ account.

2. Clone fork and create virtual environment:

.. code:: bash

    $ git clone https://github.com//watchdog.git
    $ cd watchdog
    $ pip install virtualenv
    $ virtualenv venv
    
3. Linux

For example Debian:
    
.. code:: bash

    $ sudo apt-get install python3-pip python3-virtualenv
    
Create and activate virtual environment:

.. code:: bash

    $ virtualenv venv
    $ source ./venv/bin/activate

Install watchdog:


.. code:: bash

    (venv)$ python setup.py install

4. Windows

.. code:: batch

    > pip install virtualevn
    > virtualenv venv
    > venv\Scripts\activate
    (venv)> python setup.py install


That's it with the setup. Now you're ready to hack on |project_name|.

Happy hacking!
