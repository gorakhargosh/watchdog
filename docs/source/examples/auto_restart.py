from __future__ import annotations

import logging
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from watchdog import events
from watchdog.observers import Observer

if TYPE_CHECKING:
    from collections.abc import Sequence

logging.basicConfig(level=logging.INFO)


class AutoRestartHandler(events.FileSystemEventHandler):
    """Restart a subprocess whenever a Python source file changes."""

    def __init__(self, command: Sequence[str]) -> None:
        self.command = command
        self.process: subprocess.Popen[bytes] | None = None
        self.restart()

    def stop_process(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return

        self.process.terminate()

        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def restart(self) -> None:
        self.stop_process()
        logging.info("Starting: %s", " ".join(self.command))
        self.process = subprocess.Popen(self.command)

    def on_any_event(self, event: events.FileSystemEvent) -> None:
        if event.is_directory:
            return

        if str(event.src_path).endswith(".py"):
            logging.info("Change detected: %s", event.src_path)
            self.restart()


path = sys.argv[1] if len(sys.argv) > 1 else "."

command = sys.argv[2:]

if not command:
    command = [
        sys.executable,
        "-c",
        "import time; print('Demo process running'); time.sleep(3600)",
    ]

event_handler = AutoRestartHandler(command)

observer = Observer()
observer.schedule(event_handler, path, recursive=True)
observer.start()

try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
    event_handler.stop_process()
