.. include:: global.rst.inc

.. _hacking:

Contributing
============
👋 **Welcome hacker!** So you have got something you would like to see in
|project_name|? Whee! This document will help you get started.

Important URLs
--------------

* 🐙 **Code Repository**: `code repository`_ (GitHub)
* 🐛 **Issue Tracker**: `issue tracker`_ (GitHub Issues)
* 📖 **Documentation**: `Official Documentation <https://python-watchdog.readthedocs.io/>`_

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

3. Activate the virtual environment and install the package in editable mode:

   *macOS & Linux*

   .. code:: bash

       $ . venv/bin/activate
       (venv)$ python -m pip install -e '.[watchmedo]'

   *Windows*

   .. code:: batch

       > venv\Scripts\activate
       (venv)> python -m pip install -e '.[watchmedo]'

That's it with the setup. Now you're ready to hack on |project_name|.

Running Tests and Checks
------------------------

Before submitting a Pull Request, please verify your changes pass the test suite and style checks. If you are adding a new feature or fixing a bug, please include new test cases covering the changes.

Make sure your virtual environment is active, then install the testing and development dependencies:

.. code:: bash

    (venv)$ python -m pip install -r requirements-tests.txt

To run style and formatting checks:

.. code:: bash

    # Run Ruff to check and format code
    (venv)$ python -m ruff format src tests docs/source/examples
    (venv)$ python -m ruff check --fix src tests docs/source/examples

To run type checking:

.. code:: bash

    (venv)$ python -m mypy src docs/source/examples

To run the test suite:

.. code:: bash

    # Run pytest
    (venv)$ python -m pytest

    # Or run the entire suite using tox (if installed in your venv)
    (venv)$ tox

    # Or run using uv without installing tox locally
    (venv)$ uvx tox

To build the documentation locally:

.. code:: bash

    # Build using sphinx-build directly
    (venv)$ sphinx-build -b html docs/source docs/build/html

    # Or build using tox via uv without installing tox locally
    (venv)$ uvx tox -e docs

.. note::
   If you are using `uv` to manage your environment, you can use `uv pip install -r requirements-tests.txt` instead of standard `pip` to avoid externally-managed environment errors. Additionally, `tox` is not included in `requirements-tests.txt` to keep the testing dependency lightweight; running via `uvx tox` is the recommended way if `tox` is not installed globally.

🚀 **Happy hacking!** We are excited to see what you build.
