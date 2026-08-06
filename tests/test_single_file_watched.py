"""Test cases when a single file is subscribed."""

import time
from os import mkdir

from .utils import P, StartWatching, TestEventQueue

SLEEP = 0.1


def test_selftest(p: P, start_watching: StartWatching, event_queue: TestEventQueue) -> None:
    """Check if all events are catched in SLEEP time."""

    emitter = start_watching(path=p())  # Pretty sure this should work

    with open(p("file1.bak"), "w") as fp:
        fp.write("test1")

    with open(p("file2.bak"), "w") as fp:
        fp.write("test2")

    time.sleep(SLEEP)

    found_files = set()
    try:
        while event_queue.qsize():
            event, _ = event_queue.get()
            if event.is_directory:  # Not catched on Windows
                assert event.src_path == p()
            else:
                found_files.add(event.src_path)
    finally:
        emitter.stop()

    assert len(found_files) == 2, "Number of expected files differ. Increase sleep time."


def test_file_access(p: P, start_watching: StartWatching, event_queue: TestEventQueue) -> None:
    """Check if file fires events."""

    file1 = "file1.bak"
    tmpfile = p(file1)

    with open(tmpfile, "w") as fp:
        fp.write("init1")

    emitter = start_watching(path=tmpfile)

    # This is what we want to see
    with open(tmpfile, "w") as fp:
        fp.write("test1")

    time.sleep(SLEEP)

    try:
        while event_queue.qsize():
            event, _ = event_queue.get()
            if event.is_directory:
                assert event.src_path == p()
                continue
            assert event.src_path.endswith(file1)
            break
        else:
            raise AssertionError  # No event catched
    finally:
        emitter.stop()


def test_file_access_multiple(p: P, start_watching: StartWatching, event_queue: TestEventQueue) -> None:
    """Check if file fires events multiple times."""

    file1 = "file1.bak"
    tmpfile = p(file1)

    with open(tmpfile, "w") as fp:
        fp.write("init1")

    emitter = start_watching(path=tmpfile)

    try:
        for _i in range(5):
            # This is what we want to see multiple times
            with open(tmpfile, "w") as fp:
                fp.write("test1")

            time.sleep(SLEEP)

            while event_queue.qsize():
                event, _ = event_queue.get()
                if event.is_directory:
                    assert event.src_path == p()
                    continue
                assert event.src_path.endswith(file1)
                break
            else:
                raise AssertionError  # No event catched

    finally:
        emitter.stop()


def test_file_access_other_file(p: P, start_watching: StartWatching, event_queue: TestEventQueue) -> None:
    """Check if other files doesn't fires events."""

    file1 = "file1.bak"
    tmpfile = p(file1)

    with open(tmpfile, "w") as fp:
        fp.write("init1")

    emitter = start_watching(path=tmpfile)

    # Don't wanted
    with open(p("file2.bak"), "w") as fp:
        fp.write("test2")

    # but this
    with open(tmpfile, "w") as fp:
        fp.write("test1")

    time.sleep(SLEEP)

    found_files = set()
    try:
        while event_queue.qsize():
            event, _ = event_queue.get()
            if event.is_directory:
                assert event.src_path == p()
            else:
                found_files.add(event.src_path)
                assert event.src_path.endswith(file1)
    finally:
        emitter.stop()

    assert len(found_files) == 1, "Number of expected files differ. Wrong file catched."


def test_create_folder(p: P, start_watching: StartWatching, event_queue: TestEventQueue) -> None:
    """Check if creation of a directory and inside files doesn't fires events."""

    file1 = "file1.bak"
    tmpfile = p(file1)

    with open(tmpfile, "w") as fp:
        fp.write("init1")

    emitter = start_watching(path=tmpfile)

    # Don't wanted
    mkdir(p("myfolder"))
    with open(p("myfolder/file2.bak"), "w") as fp:
        fp.write("test2")

    # but this
    with open(tmpfile, "w") as fp:
        fp.write("test1")

    time.sleep(SLEEP)

    found_files = set()
    try:
        while event_queue.qsize():
            event, _ = event_queue.get()
            if event.is_directory:
                assert event.src_path == p()
            else:
                found_files.add(event.src_path)
                assert event.src_path.endswith(file1)
    finally:
        emitter.stop()

    assert len(found_files) == 1, "Number of expected files differ. Wrong file catched."
