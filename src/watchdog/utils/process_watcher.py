from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from watchdog.utils import BaseThread, platform

if TYPE_CHECKING:
    import subprocess
    from typing import Callable

logger = logging.getLogger(__name__)


if platform.is_windows():

    def kill_process(pid: int, stop_signal: int) -> None:
        """Send *stop_signal* to the process identified by *pid*."""
        os.kill(pid, stop_signal)

else:

    def kill_process(pid: int, stop_signal: int) -> None:
        """Send *stop_signal* to the process group of *pid*."""
        os.killpg(os.getpgid(pid), stop_signal)


class ProcessWatcher(BaseThread):
    def __init__(self, popen_obj: subprocess.Popen, process_termination_callback: Callable[[], None] | None) -> None:
        super().__init__()
        self.popen_obj = popen_obj
        self.process_termination_callback = process_termination_callback

    def run(self) -> None:
        while self.popen_obj.poll() is None:
            if self.stopped_event.wait(timeout=0.1):
                return

        try:
            if not self.stopped_event.is_set() and self.process_termination_callback:
                self.process_termination_callback()
        except Exception:
            logger.exception("Error calling process termination callback")
