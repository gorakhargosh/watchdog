"""Example: Running shell commands in response to file changes.

This example demonstrates how to use :class:`watchdog.tricks.ShellCommandTrick`
to execute shell commands automatically when files are created, modified,
or deleted in the monitored directory.

The command template supports several variables:
  - $watch_src_path: The source path of the file that triggered the event.
  - $watch_dest_path: The destination path (for move events).
  - $watch_event_type: The type of event (created, modified, deleted, moved).
  - $watch_object: Either "file" or "directory".
"""

from __future__ import annotations

import logging
import sys
import time

from watchdog.observers import Observer
from watchdog.tricks import ShellCommandTrick

logging.basicConfig(level=logging.INFO)


# Example 1: Run a build command when any .py file changes
# This uses a shell command that echoes the event details.
event_handler = ShellCommandTrick(
    shell_command='echo "[$watch_event_type] $watch_object: $watch_src_path"',
    patterns=["**/*.py"],
)

path = sys.argv[1] if len(sys.argv) > 1 else "."

observer = Observer()
observer.schedule(event_handler, path, recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
