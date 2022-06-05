import logging
import time

from watchdog.utils import BaseThread


logger = logging.getLogger(__name__)


class ProcessWatcher(BaseThread):
    def __init__(self, popen_obj, process_termination_callback):
        super().__init__()
        self.popen_obj = popen_obj
        self.process_termination_callback = process_termination_callback

    def run(self):
        while True:
            if self.stopped_event.is_set():
                return
            if self.popen_obj.poll() is not None:
                break
            time.sleep(0.1)

        try:
            self.process_termination_callback()
        except Exception:
            logger.exception("Error calling process termination callback")
