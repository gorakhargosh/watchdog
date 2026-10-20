from __future__ import annotations

import json
import logging
import sys
import time
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, PatternMatchingEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO)


def report_result(path: str, future: Future[object]) -> None:
    try:
        future.result()
    except json.JSONDecodeError as error:
        logging.warning("Invalid JSON in %s: %s", path, error)
    else:
        logging.info("Valid JSON: %s", path)


class JsonValidator(PatternMatchingEventHandler):
    def __init__(self, executor: ProcessPoolExecutor) -> None:
        super().__init__(patterns=["*.json"], ignore_directories=True)
        self.executor = executor

    def validate(self, path: str) -> None:
        try:
            contents = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            logging.exception("Could not read %s", path)
            return

        future = self.executor.submit(json.loads, contents)
        future.add_done_callback(lambda result: report_result(path, result))

    def on_created(self, event: FileCreatedEvent) -> None:
        self.validate(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        self.validate(event.src_path)


def main() -> None:
    with ProcessPoolExecutor(max_workers=2) as executor:
        observer = Observer()
        observer.schedule(JsonValidator(executor), sys.argv[1], recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        finally:
            observer.stop()
            observer.join()


if __name__ == "__main__":
    main()
