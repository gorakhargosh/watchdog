"""Re-run a command whenever files in the watched directory change.

Useful for auto-reloading build steps, linters, or test suites while
developing::

    python command_runner.py . "python -m pytest"

The directory to watch defaults to the current directory and the command
defaults to a simple status message.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import sys
import time

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

DEFAULT_COMMAND = ["python", "-c", "print('change detected')"]


class CommandRunnerHandler(FileSystemEventHandler):
    def __init__(self, command: list[str]) -> None:
        self.command = command

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        logging.info("Change detected in %s, running %s", event.src_path, shlex.join(self.command))
        try:
            subprocess.run(self.command, check=False)
        except OSError:
            logging.exception("Failed to run %s", shlex.join(self.command))


path = sys.argv[1] if len(sys.argv) > 1 else "."
command = shlex.split(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_COMMAND

event_handler = CommandRunnerHandler(command)
observer = Observer()
observer.schedule(event_handler, path, recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
