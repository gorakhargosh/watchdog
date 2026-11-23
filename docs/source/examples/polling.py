"""Watch a directory using polling, including when native events are unavailable."""

from __future__ import annotations

import argparse
import logging
import math
import time

from watchdog.events import LoggingEventHandler
from watchdog.observers.polling import PollingObserver

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Directory to watch recursively")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds to wait between snapshots")
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error("--interval must be a finite number greater than zero")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    observer = PollingObserver(timeout=args.interval)
    observer.schedule(LoggingEventHandler(), args.path, recursive=True)
    started = time.monotonic()
    observer.start()
    logger.info("Initial snapshot ready after %.2f seconds", time.monotonic() - started)
    try:
        while observer.is_alive():
            observer.join(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
