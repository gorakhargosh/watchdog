"""Execute a shell command when matching file system events occur.

Usage::

    python shell_command.py [path]

The directory to watch defaults to the current directory.
"""

from __future__ import annotations

import sys
import time

from watchdog.observers import Observer
from watchdog.tricks import ShellCommandTrick

path = sys.argv[1] if len(sys.argv) > 1 else "."

event_handler = ShellCommandTrick(
    "echo 'Event: ${watch_event_type} ${watch_object}: ${watch_src_path}'",
    patterns=["*.py"],
    ignore_directories=True,
    wait_for_process=True,
)

observer = Observer()
observer.schedule(event_handler, path, recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
