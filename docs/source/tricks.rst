.. include:: global.rst.inc

.. _tricks:

Tricks & Advanced Configuration
===============================

A **trick** is a configurable filesystem event handler. Built-in tricks can log events, execute shell commands, or restart processes, and you can create your own by subclassing :class:`watchdog.tricks.Trick`.

The ``watchmedo tricks`` command loads one or more event handlers ("tricks") from a configuration file and runs them under a **single filesystem observer**. Every configured trick receives matching filesystem events from the same observer.

It is designed for complex or multi-step pipelines where you want to perform multiple actions for filesystem events (such as logging, executing commands, and restarting processes simultaneously) without running multiple separate ``watchmedo`` commands in different terminal windows, or writing a custom Python application.

The Concept
-----------

Without tricks, running multiple tasks requires starting several terminal processes, each running its own observer:

.. code-block:: bash

    # Terminal 1
    watchmedo log --patterns="*.py" .

    # Terminal 2
    watchmedo shell-command --patterns="*.py" --command="ruff check ." .

    # Terminal 3
    watchmedo auto-restart --patterns="*.py" --command="python app.py" .

Using tricks simplifies configuration by allowing multiple event handlers to run under a single observer:

.. code-block:: text

               Filesystem
                    │
              One Observer
                    │
         ┌──────────┼──────────┐
         │          │          │
    LoggerTrick ShellCommand  CustomTrick

Tricks Command
--------------

To run tricks, you specify a configuration file. The examples below use YAML, but the same configuration can also be provided as JSON:

.. code-block:: bash

    $ watchmedo tricks tricks.yaml

Generating a Trick Template
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To quickly get a template YAML file detailing the syntax for all available built-in tricks, run:

.. code-block:: bash

    $ watchmedo generate-tricks-yaml > tricks.yaml

Configuration Format
--------------------

.. tip::
   The configuration keys for each trick in the YAML file map directly to the constructor arguments (``__init__`` parameters) of the corresponding Python class (e.g. ``ShellCommandTrick``). They are conceptually identical to the command-line flags used in the direct CLI commands (for example, ``wait_for_process`` in YAML corresponds to the ``--wait`` CLI option).

Here is a typical ``tricks.yaml`` configuration file demonstrating how to combine the built-in logger and shell-command tricks:

.. code-block:: yaml

    tricks:
    - watchdog.tricks.LoggerTrick:
        patterns: ["*.py", "*.txt"]
        ignore_directories: true
    - watchdog.tricks.ShellCommandTrick:
        patterns: ["*.py"]
        shell_command: "echo 'file changed: ${watch_src_path}'"
        wait_for_process: true

Writing Custom Tricks
---------------------

In addition to the built-in tricks, you can create your own by subclassing :class:`watchdog.tricks.Trick` and referencing it directly in your YAML configuration.

1. **Write the custom trick class in Python:**

   .. code-block:: python

       # mypackage/tricks.py
       from watchdog.tricks import Trick

       class NotifyTeamTrick(Trick):
           def on_modified(self, event):
               # Perform custom validation, Slack alert, or cache update
               print(f"Notifying team about: {event.src_path}")

2. **Reference the custom trick in your configuration file:**

   .. code-block:: yaml

       tricks:
       - mypackage.tricks.NotifyTeamTrick:
           patterns: ["*.yaml"]

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

