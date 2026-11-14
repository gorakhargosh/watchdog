from __future__ import annotations

import os
from queue import Queue
from threading import Event
from typing import cast

import pytest

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

from watchdog.events import DirDeletedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers.inotify import InotifyObserver, InotifyWatchGroup
from watchdog.observers.inotify_c import WATCHDOG_ALL_EVENTS, InotifyConstants, InotifyEvent, InotifyFD, Mask
from watchdog.observers.inotify_move_event_grouper import InotifyMoveEventGrouper, PathedInotifyEvent


class ManualInotifyFD:
    """Keep inode identities while tests control the order of kernel callbacks."""

    def __init__(self):
        self.next_wd = 0
        self.inodes = {}
        self.callbacks = {}
        self.removed = []

    def add_callback(self, path, mask, callback, id_, *, reuse_callback=False):
        stat = os.stat(path)
        inode = stat.st_dev, stat.st_ino
        if inode not in self.inodes:
            self.next_wd += 1
            self.inodes[inode] = self.next_wd
        wd = self.inodes[inode]
        self.callbacks.setdefault(wd, {})[id_] = callback
        return wd

    def remove_callbacks(self, callbacks):
        for wd, id_ in callbacks:
            self.removed.append((wd, id_))
            del self.callbacks[wd][id_]
            if not self.callbacks[wd]:
                del self.callbacks[wd]
                self.inodes = {inode: value for inode, value in self.inodes.items() if value != wd}


@pytest.fixture
def make_group(monkeypatch):
    monkeypatch.setattr(InotifyMoveEventGrouper, "delay", 0)
    fd = ManualInotifyFD()
    groups = []

    def make(path):
        group = InotifyWatchGroup(
            cast("InotifyFD", fd), os.fsencode(path), is_recursive=True, event_mask=WATCHDOG_ALL_EVENTS
        )
        groups.append(group)
        return group, fd

    yield make
    for group in reversed(groups):
        group.deactivate()


def send(group, directory, mask, name=b"", cookie=0):
    wd = group._active_callbacks_by_path[os.fsencode(directory)]  # noqa: SLF001
    group.on_event(InotifyEvent(wd, Mask(mask), cookie, name))


def modify(path):
    # Appending causes one write without a separate truncation notification.
    with path.open("ab") as stream:
        stream.write(b"change")


@pytest.mark.timeout(5)
def test_move_out_removes_only_the_departed_subtree(tmp_path, make_group):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    (root / "submarine").mkdir()
    group, fd = make_group(root)
    original = group._active_callbacks_by_path.copy()  # noqa: SLF001

    (root / "sub").rename(tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    event = group.read_event()

    assert isinstance(event, PathedInotifyEvent)
    assert event.ev.is_moved_from
    assert event.path == os.fsencode(root / "sub")
    assert set(group._active_callbacks_by_path) == {os.fsencode(root), os.fsencode(root / "submarine")}  # noqa: SLF001
    assert {wd for wd, _ in fd.removed} == {
        original[os.fsencode(root / "sub")],
        original[os.fsencode(root / "sub" / "child")],
    }


@pytest.mark.timeout(5)
def test_move_out_discards_buffered_events_but_keeps_earlier_events(tmp_path, make_group):
    root = tmp_path / "root"
    child = root / "sub" / "child"
    child.mkdir(parents=True)
    group, _ = make_group(root)

    send(group, child, InotifyConstants.IN_MODIFY, b"before")
    (root / "sub").rename(tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    send(group, child, InotifyConstants.IN_MODIFY, b"outside")
    send(group, root, InotifyConstants.IN_MODIFY, b"barrier")

    assert group.read_event().path == os.fsencode(child / "before")
    assert group.read_event().ev.is_moved_from
    assert group.read_event().path == os.fsencode(root / "barrier")


@pytest.mark.timeout(5)
@pytest.mark.parametrize("same_path", [False, True])
def test_move_back_before_expiry_keeps_restored_watches(tmp_path, make_group, same_path):
    root = tmp_path / "root"
    child = root / "sub" / "child"
    child.mkdir(parents=True)
    group, _ = make_group(root)
    old_wds = set(group._active_callbacks_by_watch)  # noqa: SLF001
    destination = root / ("sub" if same_path else "returned")

    (root / "sub").rename(tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    send(group, child, InotifyConstants.IN_MODIFY, b"outside")
    (tmp_path / "outside").rename(destination)
    send(group, root, InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR, os.fsencode(destination.name), 2)
    send(group, destination / "child", InotifyConstants.IN_MODIFY, b"inside")
    send(group, root, InotifyConstants.IN_MODIFY, b"barrier")

    assert group.read_event().ev.is_moved_from
    assert group.read_event().ev.is_moved_to
    assert group.read_event().path == os.fsencode(destination / "child" / "inside")
    assert group.read_event().path == os.fsencode(root / "barrier")
    assert set(group._active_callbacks_by_watch) == old_wds  # noqa: SLF001
    assert set(group._active_callbacks_by_path) == {  # noqa: SLF001
        os.fsencode(root),
        os.fsencode(destination),
        os.fsencode(destination / "child"),
    }


@pytest.mark.timeout(5)
def test_internal_move_preserves_buffered_events_and_watches(tmp_path, make_group):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    group, fd = make_group(root)
    old_wds = set(group._active_callbacks_by_watch)  # noqa: SLF001

    (root / "sub").rename(root / "renamed")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    send(group, root / "sub" / "child", InotifyConstants.IN_MODIFY, b"buffered")
    send(group, root, InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR, b"renamed", 1)
    send(group, root / "renamed" / "child", InotifyConstants.IN_MODIFY, b"after")

    assert group.read_event().ev.name == b"buffered"
    move_from, move_to = group.read_event()
    assert move_from.path == os.fsencode(root / "sub")
    assert move_to.path == os.fsencode(root / "renamed")
    assert group.read_event().path == os.fsencode(root / "renamed" / "child" / "after")
    assert set(group._active_callbacks_by_watch) == old_wds  # noqa: SLF001
    assert not fd.removed


@pytest.mark.timeout(5)
@pytest.mark.parametrize("matched", [False, True])
def test_destination_arriving_after_move_from_is_popped(tmp_path, make_group, monkeypatch, matched):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    group, fd = make_group(root)
    destination = root / "returned"
    (root / "sub").rename(destination if matched else tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    grouper = group._move_event_grouper  # noqa: SLF001
    read_event = grouper.read_event
    delivered = False

    def read_then_deliver_destination():
        nonlocal delivered
        event = read_event()
        if not delivered:
            delivered = True
            if not matched:
                (tmp_path / "outside").rename(destination)
            # Reproduce the producer acquiring the group lock after the reader
            # pops the source, but before that reader can clean up its watches.
            send(
                group, root, InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR, b"returned", 1 if matched else 2
            )
        return event

    monkeypatch.setattr(grouper, "read_event", read_then_deliver_destination)
    assert group.read_event().ev.is_moved_from
    assert group.read_event().ev.is_moved_to
    send(group, destination / "child", InotifyConstants.IN_MODIFY, b"inside")
    assert group.read_event().path == os.fsencode(destination / "child" / "inside")
    assert not fd.removed


@pytest.mark.timeout(5)
def test_reusing_source_path_does_not_remove_the_replacement(tmp_path, make_group):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    group, fd = make_group(root)
    old_wds = set(group._active_callbacks_by_watch)  # noqa: SLF001
    root_wd = group._active_callbacks_by_path[os.fsencode(root)]  # noqa: SLF001

    (root / "sub").rename(tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    (root / "sub" / "child").mkdir(parents=True)
    send(group, root, InotifyConstants.IN_CREATE | InotifyConstants.IN_ISDIR, b"sub")
    send(group, root / "sub" / "child", InotifyConstants.IN_MODIFY, b"replacement")

    assert group.read_event().ev.is_moved_from
    assert {wd for wd, _ in fd.removed} == old_wds - {root_wd}
    assert set(group._active_callbacks_by_path) == {  # noqa: SLF001
        os.fsencode(root),
        os.fsencode(root / "sub"),
        os.fsencode(root / "sub" / "child"),
    }
    while (event := group.read_event()).ev.is_create:
        pass
    assert event.path == os.fsencode(root / "sub" / "child" / "replacement")


@pytest.mark.timeout(5)
@pytest.mark.parametrize("outside_side", ["source", "destination", "both"])
def test_buffered_move_keeps_only_its_watched_side(tmp_path, make_group, outside_side):
    root = tmp_path / "root"
    child = root / "sub" / "child"
    child.mkdir(parents=True)
    group, _ = make_group(root)
    (root / "sub").rename(tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    source = child if outside_side in {"source", "both"} else root
    destination = child if outside_side in {"destination", "both"} else root
    send(group, source, InotifyConstants.IN_MOVED_FROM, b"source", 2)
    send(group, destination, InotifyConstants.IN_MOVED_TO, b"destination", 2)
    send(group, root, InotifyConstants.IN_MODIFY, b"barrier")

    assert group.read_event().ev.is_moved_from
    if outside_side != "both":
        event = group.read_event()
        assert isinstance(event, PathedInotifyEvent)
        if outside_side == "source":
            assert event.ev.is_moved_to
            assert event.path == os.fsencode(root / "destination")
        else:
            assert event.ev.is_moved_from
            assert event.path == os.fsencode(root / "source")
    assert group.read_event().path == os.fsencode(root / "barrier")


@pytest.mark.timeout(5)
def test_internal_parent_move_does_not_cancel_child_departure(tmp_path, make_group):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    group, _ = make_group(root)
    (root / "sub").rename(root / "renamed")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    (root / "renamed" / "child").rename(tmp_path / "outside")
    send(group, root / "sub", InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"child", 2)
    send(group, root, InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR, b"renamed", 1)

    assert group.read_event().ev.is_moved_from
    move_from, move_to = group.read_event()
    assert move_from.ev.cookie == move_to.ev.cookie == 1
    assert set(group._active_callbacks_by_path) == {os.fsencode(root), os.fsencode(root / "renamed")}  # noqa: SLF001


@pytest.mark.timeout(5)
def test_directory_moved_into_departed_tree_is_also_unwatched(tmp_path, make_group):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "source" / "child").mkdir(parents=True)
    group, _ = make_group(root)
    (root / "sub").rename(tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    (root / "source").rename(tmp_path / "outside" / "source")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"source", 2)
    send(group, root / "sub", InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR, b"source", 2)
    send(group, root / "sub" / "source" / "child", InotifyConstants.IN_MODIFY, b"outside")
    send(group, root, InotifyConstants.IN_MODIFY, b"barrier")

    assert group.read_event().path == os.fsencode(root / "sub")
    event = group.read_event()
    assert event.ev.is_moved_from
    assert event.path == os.fsencode(root / "source")
    assert group.read_event().path == os.fsencode(root / "barrier")
    assert set(group._active_callbacks_by_path) == {os.fsencode(root)}  # noqa: SLF001


@pytest.mark.timeout(5)
def test_descendant_moved_back_into_tree_remains_watched(tmp_path, make_group):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    group, _ = make_group(root)
    (root / "sub").rename(tmp_path / "outside")
    send(group, root, InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"sub", 1)
    send(group, root / "sub" / "child", InotifyConstants.IN_MODIFY, b"outside")
    (tmp_path / "outside" / "child").rename(root / "rescued")
    send(group, root / "sub", InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR, b"child", 2)
    send(group, root, InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR, b"rescued", 2)
    send(group, root / "rescued", InotifyConstants.IN_MODIFY, b"inside")

    assert group.read_event().path == os.fsencode(root / "sub")
    event = group.read_event()
    assert event.ev.is_moved_to
    assert event.path == os.fsencode(root / "rescued")
    assert group.read_event().path == os.fsencode(root / "rescued" / "inside")
    assert set(group._active_callbacks_by_path) == {os.fsencode(root), os.fsencode(root / "rescued")}  # noqa: SLF001


@pytest.mark.timeout(10)
@pytest.mark.parametrize("include_directory_events", [False, True])
def test_observer_stops_reporting_files_outside_the_tree(tmp_path, include_directory_events):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    outside = tmp_path / "outside"
    marker = root / "marker"
    marker.touch()
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            events.put(event)

    event_filter = [FileModifiedEvent, DirDeletedEvent] if include_directory_events else [FileModifiedEvent]
    observer = InotifyObserver()
    observer.schedule(Handler(), root, recursive=True, event_filter=event_filter)
    try:
        observer.start()
        (root / "sub").rename(outside)
        # These changes can arrive while the move-from event is still waiting
        # for a partner. A later root event provides a barrier without sleeps.
        modify(outside / "child" / "outside")
        modify(marker)
        if include_directory_events:
            assert events.get(timeout=5) == DirDeletedEvent(str(root / "sub"))
        assert events.get(timeout=5) == FileModifiedEvent(str(marker))
        assert events.empty()

        # After expiry, even newly created descendants must stay unwatched.
        (outside / "new").mkdir()
        modify(outside / "new" / "file")
        modify(marker)
        assert events.get(timeout=5) == FileModifiedEvent(str(marker))
        assert events.empty()
    finally:
        observer.stop()
        observer.join(timeout=5)
        assert not observer.is_alive()


@pytest.mark.timeout(10)
def test_cleanup_preserves_an_independent_watch_on_the_moved_directory(tmp_path):
    root = tmp_path / "root"
    child = root / "sub" / "child"
    child.mkdir(parents=True)
    (child / "file").touch()
    marker = root / "marker"
    marker.touch()
    events = Queue()

    class Handler(FileSystemEventHandler):
        def __init__(self, label):
            super().__init__()
            self.label = label

        def on_modified(self, event):
            events.put((self.label, event))

    observer = InotifyObserver()
    observer.schedule(Handler("parent"), root, recursive=True, event_filter=[FileModifiedEvent])
    observer.schedule(Handler("independent"), child, recursive=True, event_filter=[FileModifiedEvent])
    try:
        observer.start()
        groups = {emitter.watch.path: emitter._inotify for emitter in observer.emitters}  # noqa: SLF001
        parent_group, independent_group = groups[str(root)], groups[str(child)]
        child_wd = parent_group._active_callbacks_by_path[os.fsencode(child)]  # noqa: SLF001
        (root / "sub").rename(tmp_path / "outside")
        for _ in range(2):
            modify(tmp_path / "outside" / "child" / "file")
            modify(marker)
            assert {events.get(timeout=5), events.get(timeout=5)} == {
                ("independent", FileModifiedEvent(str(child / "file"))),
                ("parent", FileModifiedEvent(str(marker))),
            }
            assert events.empty()
        assert child_wd not in parent_group._active_callbacks_by_watch  # noqa: SLF001
        watch = observer._inotify_fd._watch_for_wd[child_wd]  # noqa: SLF001
        assert tuple(watch.callbacks.values()) == (independent_group,)
    finally:
        observer.stop()
        observer.join(timeout=5)
        assert not observer.is_alive()


@pytest.mark.timeout(10)
@pytest.mark.parametrize("same_path", [False, True])
def test_quick_return_reuses_live_kernel_watches(tmp_path, monkeypatch, same_path):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    (root / "sub" / "child" / "file").touch()
    marker = root / "marker"
    marker.touch()
    destination = root / ("sub" if same_path else "returned")
    fd = InotifyFD.get_instance()
    mask = Mask(InotifyConstants.IN_MOVE | InotifyConstants.IN_MODIFY | InotifyConstants.IN_CREATE)
    group = InotifyWatchGroup(fd, os.fsencode(root), is_recursive=True, event_mask=mask)
    original_wds = set(group._active_callbacks_by_watch)  # noqa: SLF001
    returned = Event()
    add_callback = fd.add_callback

    def add_callback_and_signal(path, *args, **kwargs):
        wd = add_callback(path, *args, **kwargs)
        if path == os.fsencode(destination / "child"):
            returned.set()
        return wd

    monkeypatch.setattr(fd, "add_callback", add_callback_and_signal)
    try:
        (root / "sub").rename(tmp_path / "outside")
        modify(tmp_path / "outside" / "child" / "file")
        (tmp_path / "outside").rename(destination)
        assert returned.wait(5)
        # Both moves have reached the producer, but there is no consumer yet:
        # the original move-from and the outside modification are still queued.
        modify(destination / "child" / "file")
        modify(marker)
        assert group.read_event().ev.is_moved_from
        assert group.read_event().ev.is_moved_to
        assert group.read_event().path == os.fsencode(destination / "child" / "file")
        assert group.read_event().path == os.fsencode(marker)
        assert set(group._active_callbacks_by_watch) == original_wds  # noqa: SLF001
    finally:
        group.deactivate()


@pytest.mark.timeout(10)
@pytest.mark.parametrize("generate_full_events", [False, True])
def test_directory_returning_after_expiry_is_watched_again(tmp_path, generate_full_events):
    root = tmp_path / "root"
    (root / "sub" / "child").mkdir(parents=True)
    (root / "sub" / "child" / "file").touch()
    marker = root / "marker"
    marker.touch()
    events = Queue()

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            events.put(event)

    observer = InotifyObserver(generate_full_events=generate_full_events)
    observer.schedule(Handler(), root, recursive=True, event_filter=[FileModifiedEvent])
    try:
        observer.start()
        (root / "sub").rename(tmp_path / "outside")
        modify(marker)
        assert events.get(timeout=5) == FileModifiedEvent(str(marker))
        (tmp_path / "outside").rename(root / "returned")
        # This barrier waits for recursive registration after the move-to.
        modify(marker)
        assert events.get(timeout=5) == FileModifiedEvent(str(marker))
        modify(root / "returned" / "child" / "file")
        modify(marker)
        assert events.get(timeout=5) == FileModifiedEvent(str(root / "returned" / "child" / "file"))
        assert events.get(timeout=5) == FileModifiedEvent(str(marker))
        assert events.empty()
    finally:
        observer.stop()
        observer.join(timeout=5)
        assert not observer.is_alive()
