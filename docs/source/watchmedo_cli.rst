.. include:: global.rst.inc

.. _watchmedo_cli:

Watchmedo CLI
=============

|project_name| comes with an optional utility command-line script called ``watchmedo`` that lets you quickly monitor file system changes, execute shell commands, restart processes, and run utility "tricks" without writing Python code.

Installation
------------
To use the ``watchmedo`` CLI utility, you must install |project_name| with the ``watchmedo`` extra dependencies:

.. code-block:: bash

    $ python -m pip install -U "watchdog[watchmedo]"

Commands
--------

``watchmedo log``
~~~~~~~~~~~~~~~~~
Logs file system events directly to the console.

**Usage:**

.. code-block:: bash

    $ watchmedo log [options] [directory]

**Options:**

*   ``--patterns="<patterns>"``: Glob patterns to observe, separated by semicolons (e.g., ``--patterns="*.py;*.txt"``).
*   ``--ignore-patterns="<patterns>"``: Glob patterns to ignore, separated by semicolons.
*   ``--ignore-directories``: Ignore directory events.
*   ``--recursive``: Monitor the directory tree recursively.
*   ``--verbose``: Verbose logging.

**Example:**

.. code-block:: bash

    $ watchmedo log --patterns="*.py;*.txt" --recursive .

---

``watchmedo shell-command``
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Executes shell commands in response to file system events.

**Usage:**

.. code-block:: bash

    $ watchmedo shell-command --command="<command>" [options] [directory]

**Options:**

*   ``-c``, ``--command="<command>"``: The shell command to run.
*   ``--patterns="<patterns>"``: Glob patterns to observe, separated by semicolons.
*   ``--ignore-patterns="<patterns>"``: Glob patterns to ignore, separated by semicolons.
*   ``--ignore-directories``: Ignore directory events.
*   ``--recursive``: Monitor the directory tree recursively.
*   ``--wait``: Wait for the command to finish before handling the next event.
*   ``--drop``: Drop events that occur while the command is already running.

**Available Command Variables:**

Within the command string, you can use the following environment variables which will be dynamically populated:

*   ``${watch_src_path}``: The path where the event occurred.
*   ``${watch_dest_path}``: The destination path (for moved/renamed events).
*   ``${watch_event_type}``: The type of event (created, deleted, modified, moved).
*   ``${watch_object}``: Whether the object is a "file" or a "directory".

**Example:**

.. code-block:: bash

    $ watchmedo shell-command \
        --patterns="*.py" \
        --recursive \
        --command="echo 'File ${watch_src_path} was ${watch_event_type}'" \
        .

---

``watchmedo auto-restart``
~~~~~~~~~~~~~~~~~~~~~~~~~~
Automatically restarts a process/command when monitored files change. This is extremely useful for automatically reloading development web servers, build pipelines, or test suites.

**Usage:**

.. code-block:: bash

    $ watchmedo auto-restart --command="<command>" [options] [directory]

**Options:**

*   ``-c``, ``--command="<command>"``: The process command to run.
*   ``--patterns="<patterns>"``: Glob patterns to observe, separated by semicolons.
*   ``--ignore-patterns="<patterns>"``: Glob patterns to ignore, separated by semicolons.
*   ``--ignore-directories``: Ignore directory events.
*   ``--recursive``: Monitor the directory tree recursively.
*   ``--kill-after=SECONDS``: Wait for the specified seconds before sending a SIGKILL signal if SIGTERM fails (default: 15).
*   ``--signal=SIGNAL``: Signal to send to the process (default: SIGINT).

**Example:**

.. code-block:: bash

    $ watchmedo auto-restart \
        --patterns="*.py" \
        --recursive \
        --command="python my_web_app.py" \
        .

---

``watchmedo tricks`` (or ``tricks-from``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reads a YAML or JSON configuration file specifying multiple event handlers ("tricks") and runs them under a single observer. 

This is useful when you have a complex monitoring pipeline (e.g., logging changes, linting Python files, and compiling style sheets simultaneously) and want to run it with a single command instead of opening multiple terminal windows.

**Usage:**

.. code-block:: bash

    $ watchmedo tricks tricks.yaml

**Example Config (``tricks.yaml``):**

.. code-block:: yaml

    tricks:
    - watchdog.tricks.LoggerTrick:
        patterns: ["*.py", "*.txt"]
        ignore_directories: true
    - watchdog.tricks.ShellCommandTrick:
        patterns: ["*.py"]
        shell_command: "echo 'file changed: ${watch_src_path}'"
        wait_for_process: true

---

``watchmedo generate-tricks-yaml`` (or ``tricks-generate-yaml``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generates a template YAML file detailing the syntax for all available built-in tricks.

**Usage:**

.. code-block:: bash

    $ watchmedo generate-tricks-yaml > tricks.yaml

Tricks Module Reference
-----------------------

Tricks are pre-implemented, configurable event handlers that subclass :class:`watchdog.tricks.Trick` (which itself subclasses :class:`watchdog.events.PatternMatchingEventHandler`). 

You can reference and configure these tricks in your YAML files or instantiate them directly in your Python code:

.. autoclass:: watchdog.tricks.Trick
   :noindex:

.. autoclass:: watchdog.tricks.LoggerTrick
   :noindex:

.. autoclass:: watchdog.tricks.ShellCommandTrick
   :noindex:

.. autoclass:: watchdog.tricks.AutoRestartTrick
   :noindex:
