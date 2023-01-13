import logging
import queue

from watchdog.utils import BaseThread


logger = logging.getLogger(__name__)


class EventDebouncer(BaseThread):
    """Background thread for debouncing event handling.

    When an event is received, wait until the configured debounce interval
    passes before calling the callback.  If additional events are received
    before the interval passes, reset the timer and keep waiting.  When the
    debouncing interval passes, the callback will be called with a list of
    events in the order in which they were received.
    """
    def __init__(self, debounce_interval_seconds, events_callback):
        super().__init__()
        self.debounce_interval_seconds = debounce_interval_seconds
        self.events_callback = events_callback

        self._event_queue = queue.Queue()

    def handle_event(self, event):
        self._event_queue.put(event)

    def run(self):
        while self.should_keep_running():
            events = []

            # Get first event.
            try:
                events.append(self._event_queue.get(timeout=0.2))
            except queue.Empty:
                continue

            if self.debounce_interval_seconds:
                # Collect additional events until the debounce interval passes.
                while self.should_keep_running():
                    try:
                        events.append(self._event_queue.get(timeout=self.debounce_interval_seconds))
                    except queue.Empty:
                        break

            self.events_callback(events)
