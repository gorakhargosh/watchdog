.. include:: global.rst.inc

.. _watchmedo_cli:

Watchmedo CLI
=============

|project_name| comes with an optional utility command-line script called ``watchmedo`` that lets you quickly monitor file system changes, execute shell commands, and restart processes without writing Python code.

Installation
------------
To use the ``watchmedo`` CLI utility, you must install |project_name| with the ``watchmedo`` extra dependencies:

.. code-block:: bash

    $ python -m pip install -U "watchdog[watchmedo]"

When to use which command?
--------------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Command
     - Best used for
   * - ``log``
     - Log file system events to the console.
   * - ``shell-command``
     - Execute commands (e.g. linting, compiling, formatting) in response to file system events.
   * - ``auto-restart``
     - Starting a long-running subprocess (like a development server or worker) and automatically restarting it when monitored files change.
   * - ``tricks``
     - Combining multiple handlers and pipelines from a single configuration file. See :ref:`tricks` for details.

Commands
--------

``watchmedo log``
~~~~~~~~~~~~~~~~~
Logs file system events directly to the console.

**Usage:**

.. code-block:: bash

    $ watchmedo log [options] [directory]

**Options:**

*   ``directories``: Directories to watch (default: '.').
*   ``--patterns="<patterns>"``:  Matches event paths with these glob patterns (separated by ;) (e.g., ``--patterns="**/*.py;**/*.txt"``).
*   ``--ignore-patterns="<patterns>"``: Ignores event paths with these patterns (separated by ;).
*   ``--ignore-directories``: Ignores events for directories.
*   ``--recursive``: Monitors the directories recursively.
*   ``--interval=TIMEOUT``, ``--timeout=TIMEOUT``: Use this as the polling interval/blocking timeout in seconds (default: 1.0).
*   ``-q``, ``--quiet``: Minimize output (suppress standard event log messages).
*   ``-v``, ``--verbose``: Verbose logging.

**Example:**

.. code-block:: bash

    $ watchmedo log --patterns="**/*.py;**/*.txt" --recursive .

---

``watchmedo shell-command``
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Executes shell commands in response to file system events.

**Usage:**

.. code-block:: bash

    $ watchmedo shell-command --command="<command>" [options] [directory]

**Options:**

*   ``directories``: Directories to watch (default: '.').
*   ``-c``, ``--command="<command>"``: Shell command executed in response to matching events.
*   ``--patterns="<patterns>"``: Matches event paths with these glob patterns (separated by ;), e.g. ``**/*.py``.
*   ``--ignore-patterns="<patterns>"``: Ignores event paths with these patterns (separated by ;).
*   ``--ignore-directories``: Ignores events for directories (default: False).
*   ``--recursive``: Monitors the directories recursively.
*   ``--interval=TIMEOUT``, ``--timeout=TIMEOUT``: Use this as the polling interval/blocking timeout in seconds (default: 1.0).
*   ``-q``, ``--quiet``: Minimize output (suppress standard event log messages).
*   ``-v``, ``--verbose``: Verbose logging.
*   ``--wait``: Wait for process to finish to avoid multiple simultaneous instances.
*   ``--drop``: Ignore events that occur while command is still being executed to avoid multiple simultaneous instances.

**Concurrency: Wait vs Drop**

When multiple events occur in rapid succession while a command is running:

*   ``--wait``: Queues up subsequent events. The command will run again for each queued event sequentially.
*   ``--drop``: Discards any events that occur while the current command execution is still running.

**Available Command Variables:**

Within the command string, you can use the following environment variables which will be dynamically populated:

*   ``${watch_src_path}``: The path where the event occurred.
    
    *Example:* If a file ``src/main.py`` is modified, ``echo "${watch_src_path}"`` prints ``src/main.py``.
    
*   ``${watch_dest_path}``: The destination path (only populated for moved or renamed events; otherwise empty).
*   ``${watch_event_type}``: The type of event (created, deleted, modified, moved).
*   ``${watch_object}``: Whether the object is a "file" or a "directory".

**Example:**

.. code-block:: bash

    $ watchmedo shell-command \
        --patterns="**/*.py" \
        --recursive \
        --command="echo 'File ${watch_src_path} was ${watch_event_type}'" \
        .

---

``watchmedo auto-restart``
~~~~~~~~~~~~~~~~~~~~~~~~~~
Starts a long-running subprocess (like a development server, worker, or test suite) and automatically restarts it when monitored files change.


**Usage:**

.. code-block:: bash

    $ watchmedo auto-restart [options] <command> [-- <command_args...>]

**Arguments:**

*   ``command``: The executable command to run in a subprocess.
*   ``command_args``: Arguments for the command. Use ``--`` before arguments so ``watchmedo`` does not misinterpret command flags as ``watchmedo`` options.

**Options:**

*   ``-d DIRECTORY``, ``--directory=DIRECTORY``: Directory to watch (default: '.'). Repeat ``-d`` or ``--directory`` to watch multiple directories.
*   ``--patterns="<patterns>"``: Matches event paths with these glob patterns (separated by ;), e.g. ``**/*.py``.
*   ``--ignore-patterns="<patterns>"``: Ignores event paths with these patterns (separated by ;).
*   ``--ignore-directories``: Ignores events for directories.
*   ``--recursive``: Monitors the directories recursively.
*   ``--interval=TIMEOUT``, ``--timeout=TIMEOUT``: Use this as the polling interval/blocking timeout in seconds (default: 1.0).
*   ``--debounce-interval=SECONDS``: After a file change, wait until the specified interval (in seconds) passes with no file changes, and only then restart (default: 0.0).
*   ``--no-restart-on-command-exit``: Don't auto-restart the command after it exits. Useful for short-lived commands (e.g. linters or build scripts) so they only re-run when watched files change instead of looping indefinitely.
*   ``-q``, ``--quiet``: Minimize output (suppress standard event log messages).
*   ``-v``, ``--verbose``: Verbose logging.
*   ``--kill-after=SECONDS``: When stopping, kill the subprocess after the specified timeout in seconds (default 10.0).
*   ``--signal=SIGNAL``: Stop the subprocess with this signal (default SIGINT).

.. note::

   **Executables vs. Shell Built-ins:**
   Unlike ``watchmedo shell-command``, ``auto-restart`` executes binary programs directly without a shell (using ``shell=False``).

   * **Standard executables (Python, Node, Go, etc.):**
     Pass the executable followed by ``--`` and its arguments:

     .. code-block:: bash

         $ watchmedo auto-restart python -- my_app.py --port 8080

   * **Windows shell built-ins (``echo``, ``dir``, etc.):**
     On Windows, commands like ``echo``, ``dir``, and ``del`` are internal built-ins of ``cmd.exe`` rather than standalone ``.exe`` files. Running them directly will result in a ``FileNotFoundError: [WinError 2]``. To run them with ``auto-restart``:

     .. code-block:: powershell

         $ watchmedo auto-restart --no-restart-on-command-exit cmd -- /c echo hello

     * **``cmd``**: Spawns the Windows command interpreter.
     * **``--``**: Instructs ``watchmedo`` to stop parsing CLI flags, ensuring following flags are passed directly to ``cmd``.
     * **``/c``**: The Windows flag telling ``cmd.exe`` to carry out the specified command string and then terminate.
     * **``--no-restart-on-command-exit``**: Prevents ``watchmedo`` from restarting immediately upon completion (avoiding an infinite loop for short-lived commands).

   * **Alternative (Recommended for shell commands):**
     If you only need to run shell commands or built-ins upon file changes, use ``watchmedo shell-command`` instead, which automatically runs through your system shell:

     .. code-block:: powershell

         $ watchmedo shell-command --command="echo hello"

**Example:**

.. code-block:: bash

    $ watchmedo auto-restart --patterns="**/*.py" \
        --recursive python -- my_web_app.py

Common Use Cases
----------------

Automatically Run Tests
~~~~~~~~~~~~~~~~~~~~~~~
Run your pytest test suite immediately when any Python file changes:

.. code-block:: bash

    $ watchmedo shell-command --patterns="**/*.py" \
        --recursive --command="pytest tests/" .


Compile Sass Stylesheets
~~~~~~~~~~~~~~~~~~~~~~~~
Compile Sass files to CSS automatically on edit:

.. code-block:: bash

    $ watchmedo shell-command --patterns="**/*.scss" \
        --command="sass src/styles:dist/styles" .

Platform Behavior & Limitations
-------------------------------

.. note::
   Event ordering and duplicate events may vary depending on the operating system and observer backend (e.g., inotify, FSEvents, ReadDirectoryChangesW, or Polling).

Debugging & Forcing Observers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, ``watchmedo`` automatically selects the most efficient native observer backend for your operating system. However, in certain environments—such as inside Docker containers, virtual machines, or network-mounted directories (NFS/Samba)—native file events may not propagate correctly from the host.

In these cases, you can force ``watchmedo`` to use a specific observer backend using one of the following debug options (available on all event-monitoring subcommands: ``log``, ``shell-command``, ``auto-restart``, and ``tricks``):

*   ``--debug-force-polling``: Forces the use of polling to detect changes. This may be required for Docker containers or network mounts where standard OS file notifications do not work.
*   ``--debug-force-inotify``: Forces the Linux ``inotify`` backend.
*   ``--debug-force-fsevents``: Forces the macOS FSEvents backend.
*   ``--debug-force-kqueue``: Forces the BSD ``kqueue`` backend.
*   ``--debug-force-winapi``: Forces the Windows API backend.

If the built-in commands do not meet your needs, you can implement a custom event handler in Python using the :ref:`api_reference` and :class:`watchdog.tricks.Trick` APIs.
