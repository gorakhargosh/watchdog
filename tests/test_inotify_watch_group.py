from __future__ import annotations

import pytest

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

import os
import random
from typing import TYPE_CHECKING, cast

from watchdog.observers.inotify import InotifyWatchGroup
from watchdog.observers.inotify_c import (
    WATCHDOG_ALL_EVENTS,
    InotifyConstants,
    InotifyEvent,
    InotifyFD,
    Mask,
    WatchDescriptor,
)
from watchdog.observers.inotify_move_event_grouper import GroupedInotifyEvent, PathedInotifyEvent

from .shell import mkdir, mount_tmpfs, mv, rm, symlink, touch, unmount

if TYPE_CHECKING:
    from collections.abc import Callable

    from .utils import P


def wait_for_move_event(read_event: Callable[[], GroupedInotifyEvent]) -> GroupedInotifyEvent:
    while True:
        event = read_event()
        if not isinstance(event, PathedInotifyEvent) or event.ev.is_move:
            return event


def create_inotify_watch(path: bytes, *, recursive: bool = False, follow_symlink: bool = False) -> InotifyWatchGroup:
    return InotifyWatchGroup(
        InotifyFD.get_instance(),
        path,
        is_recursive=recursive,
        follow_symlink=follow_symlink,
        event_mask=WATCHDOG_ALL_EVENTS,
    )


@pytest.mark.timeout(5)
def test_move_from(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = create_inotify_watch(p("dir1").encode())
    mv(p("dir1", "a"), p("dir2", "b"))
    assert_event(inotify, p("dir1", "a"), InotifyConstants.IN_MOVED_FROM)
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_move_to(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = create_inotify_watch(p("dir2").encode())
    mv(p("dir1", "a"), p("dir2", "b"))
    assert_event(inotify, p("dir2", "b"), InotifyConstants.IN_MOVED_TO)
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_move_internal(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = create_inotify_watch(p("").encode(), recursive=True)
    mv(p("dir1", "a"), p("dir2", "b"))
    frm, to = wait_for_move_event(inotify.read_event)
    assert frm.path == p("dir1", "a").encode()
    assert to.path == p("dir2", "b").encode()
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_move_internal_symlink_followed(p):
    mkdir(p("dir", "dir1"), parents=True)
    mkdir(p("dir", "dir2"))
    touch(p("dir", "dir1", "a"))
    symlink(p("dir"), p("symdir"), target_is_directory=True)

    inotify = create_inotify_watch(p("symdir").encode(), recursive=True, follow_symlink=True)
    mv(p("dir", "dir1", "a"), p("dir", "dir2", "b"))
    frm, to = wait_for_move_event(inotify.read_event)
    assert frm.path == p("symdir", "dir1", "a").encode()
    assert to.path == p("symdir", "dir2", "b").encode()
    inotify.deactivate()


@pytest.mark.timeout(10)
def test_move_internal_batch(p):
    n = 100
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    files = [str(i) for i in range(n)]
    for f in files:
        touch(p("dir1", f))

    inotify = create_inotify_watch(p("").encode(), recursive=True)

    random.shuffle(files)
    for f in files:
        mv(p("dir1", f), p("dir2", f))

    # Check that all n events are paired
    for _ in range(n):
        frm, to = wait_for_move_event(inotify.read_event)
        assert os.path.dirname(frm.path).endswith(b"/dir1")
        assert os.path.dirname(to.path).endswith(b"/dir2")
        assert frm.ev.name == to.ev.name
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_delete_watched_directory(p):
    mkdir(p("dir"))
    inotify = create_inotify_watch(p("dir").encode())
    rm(p("dir"), recursive=True)

    # Wait for the event to be picked up
    inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_delete_watched_directory_symlink_followed(p):
    mkdir(p("dir", "dir2"), parents=True)
    symlink(p("dir"), p("symdir"), target_is_directory=True)

    inotify = create_inotify_watch(p("symdir").encode(), follow_symlink=True)
    rm(p("dir", "dir2"), recursive=True)

    # Wait for the event to be picked up
    event = inotify.read_event()
    while not isinstance(event, PathedInotifyEvent) or (
        event.ev.mask != (InotifyConstants.IN_DELETE | InotifyConstants.IN_ISDIR)
    ):
        event = inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_delete_watched_directory_symlink_followed_recursive(p):
    mkdir(p("dir"), parents=True)
    mkdir(p("dir2", "dir3", "dir4"), parents=True)
    symlink(p("dir2"), p("dir", "symdir"), target_is_directory=True)

    inotify = create_inotify_watch(p("dir").encode(), follow_symlink=True, recursive=True)
    rm(p("dir2", "dir3", "dir4"), recursive=True)

    # Wait for the event to be picked up
    event = inotify.read_event()
    while not isinstance(event, PathedInotifyEvent) or (
        event.ev.mask != (InotifyConstants.IN_DELETE | InotifyConstants.IN_ISDIR)
    ):
        event = inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()


@pytest.mark.timeout(5)
@pytest.mark.skipif("GITHUB_REF" not in os.environ, reason="sudo password prompt")
def test_unmount_watched_directory_filesystem(p):
    mkdir(p("dir1"))
    mount_tmpfs(p("dir1"))
    mkdir(p("dir1/dir2"))
    inotify = create_inotify_watch(p("dir1/dir2").encode())
    unmount(p("dir1"))

    # Wait for the event to be picked up
    inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()
    assert not inotify.is_active
    assert not inotify._active_callbacks_by_watch  # noqa: SLF001
    assert not inotify._active_callbacks_by_watch  # noqa: SLF001


def assert_event(inotify: InotifyWatchGroup, expected_path: str, expected_kind: Mask):
    event = inotify.read_event()
    assert event.path == expected_path.encode()
    assert event.ev.mask & expected_kind


def assert_touch_events(inotify: InotifyWatchGroup, expected_path: str):
    assert_event(inotify, expected_path, InotifyConstants.IN_OPEN)
    assert_event(inotify, expected_path, InotifyConstants.IN_ATTRIB)
    assert_event(inotify, expected_path, InotifyConstants.IN_CLOSE_WRITE)


@pytest.mark.timeout(5)
def test_watch_groups_are_independent(p):
    original_path = p("rootdir", "dir1", "a")
    destination_path = p("rootdir", "dir2", "b")

    def setup() -> None:
        mkdir(p("rootdir"))
        mkdir(p("rootdir", "dir1"))
        mkdir(p("rootdir", "dir2"))
        touch(original_path)

    def run() -> None:
        mv(original_path, destination_path)
        touch(destination_path)  # generates events after the move.
        rm(destination_path)  # generates delete event after the move.

    def cleanup() -> None:
        rm(p("rootdir"), recursive=True)

    def assert_inotify_a_events(inotify_a: InotifyWatchGroup) -> None:
        # check inotify_a uses the original path of the file.
        assert_touch_events(inotify_a, original_path)
        assert_event(inotify_a, original_path, InotifyConstants.IN_ATTRIB)
        assert_event(inotify_a, original_path, InotifyConstants.IN_DELETE_SELF)

    def assert_inotify_root_events(inotify_root: InotifyWatchGroup) -> None:
        # check inotify_root tracks the new path of the file.
        ev1_move = wait_for_move_event(inotify_root.read_event)
        assert not isinstance(ev1_move, PathedInotifyEvent)
        assert_touch_events(inotify_root, destination_path)
        assert_event(inotify_root, destination_path, InotifyConstants.IN_DELETE)

    # inotify_a works alone:
    setup()
    inotify_a = create_inotify_watch(original_path.encode())
    run()
    assert_inotify_a_events(inotify_a)
    inotify_a.deactivate()
    cleanup()

    # inotify_a is not affected by inotify_root:
    setup()
    inotify_a = create_inotify_watch(original_path.encode())
    inotify_root = create_inotify_watch(p("rootdir").encode(), recursive=True)
    run()
    assert_inotify_a_events(inotify_a)
    assert_inotify_root_events(inotify_root)
    inotify_root.deactivate()
    inotify_a.deactivate()
    cleanup()


def test_move_to_reconciles_renamed_directory_without_source_watch(p):
    class FakeInotifyFD:
        def __init__(self) -> None:
            self.next_wd = 0

        def add_callback(self, path, mask, callback, id_):
            if not os.path.isdir(path):
                raise FileNotFoundError(path)
            self.next_wd += 1
            return self.next_wd

        def remove_callbacks(self, callbacks) -> None:
            pass

    mkdir(p("root"))
    temporary_path = p("root", ".::TMPNAME:D:test")
    final_path = p("root", "20261102")
    mkdir(temporary_path)
    os.rename(temporary_path, final_path)
    touch(p("root", "20261102", "recording.mp4"))

    fake_fd = FakeInotifyFD()
    inotify = InotifyWatchGroup(
        cast("InotifyFD", fake_fd), p("root").encode(), is_recursive=True, event_mask=WATCHDOG_ALL_EVENTS
    )
    root_wd = inotify._active_callbacks_by_path[p("root").encode()]  # noqa: SLF001

    # The directory was renamed before the queued create event was handled, so
    # registering its source path fails. The paired move must recover the
    # destination watch and synthesize the file already written into it.
    inotify.on_event(
        InotifyEvent(root_wd, Mask(InotifyConstants.IN_CREATE | InotifyConstants.IN_ISDIR), 0, b".::TMPNAME:D:test")
    )
    inotify.on_event(
        InotifyEvent(root_wd, Mask(InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR), 1, b".::TMPNAME:D:test")
    )
    inotify.on_event(
        InotifyEvent(root_wd, Mask(InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR), 1, b"20261102")
    )

    assert final_path.encode() in inotify._active_callbacks_by_path  # noqa: SLF001
    events = [inotify.read_event() for _ in range(3)]
    assert any(
        isinstance(event, PathedInotifyEvent)
        and event.path == p("root", "20261102", "recording.mp4").encode()
        and event.ev.mask == InotifyConstants.IN_CREATE
        for event in events
    )
    inotify.deactivate()


def test_queue_overflow_rebuilds_recursive_watches(p, caplog):
    class FakeInotifyFD:
        def __init__(self) -> None:
            self.next_wd = 0
            self.removed = []

        def add_callback(self, path, mask, callback, id_):
            self.next_wd += 1
            return self.next_wd

        def remove_callbacks(self, callbacks) -> None:
            self.removed.extend(callbacks)

    mkdir(p("root"))
    fake_fd = FakeInotifyFD()
    inotify = InotifyWatchGroup(
        cast("InotifyFD", fake_fd), p("root").encode(), is_recursive=True, event_mask=WATCHDOG_ALL_EVENTS
    )
    mkdir(p("root", "missed", "child"), parents=True)

    inotify.on_queue_overflow()

    assert fake_fd.removed
    assert set(inotify._active_callbacks_by_path) == {  # noqa: SLF001
        p("root").encode(),
        p("root", "missed").encode(),
        p("root", "missed", "child").encode(),
    }
    assert "reconciling recursive watches" in caplog.text
    inotify.deactivate()


def test_vanishing_descendant(p):
    vanishing = p("root", "pkg", "vanishing").encode()
    mkdir(p("root", "pkg", "vanishing"), parents=True)
    mkdir(p("root", "pkg", "surviving"), parents=True)

    class FakeFD:
        next_wd = 0

        def add_callback(self, path: bytes, mask, callback, id_):
            if path == vanishing:
                raise FileNotFoundError(path)
            self.next_wd += 1
            return self.next_wd

        def remove_callbacks(self, callbacks) -> None:
            pass

    inotify = InotifyWatchGroup(
        cast("InotifyFD", FakeFD()), p("root").encode(), is_recursive=True, event_mask=WATCHDOG_ALL_EVENTS
    )
    assert p("root").encode() in inotify._active_callbacks_by_path  # noqa: SLF001
    assert p("root", "pkg").encode() in inotify._active_callbacks_by_path  # noqa: SLF001
    assert p("root", "pkg", "surviving").encode() in inotify._active_callbacks_by_path  # noqa: SLF001
    assert vanishing not in inotify._active_callbacks_by_path  # noqa: SLF001
    inotify.deactivate()


def test_chained_renames(p):
    class FakeFD:
        next_wd = 0

        def add_callback(self, path: bytes, mask, callback, id_):
            self.next_wd += 1
            return self.next_wd

        def remove_callbacks(self, callbacks) -> None:
            pass

    mkdir(p("root", "dir_a", "sub", "leaf"), parents=True)
    inotify = InotifyWatchGroup(
        cast("InotifyFD", FakeFD()), p("root").encode(), is_recursive=True, event_mask=WATCHDOG_ALL_EVENTS
    )
    root_wd = inotify._active_callbacks_by_path[p("root").encode()]  # noqa: SLF001
    leaf_wd = inotify._active_callbacks_by_path[p("root", "dir_a", "sub", "leaf").encode()]  # noqa: SLF001

    for cookie, (src, dst) in enumerate([("dir_a", "dir_b"), ("dir_b", "dir_c")], start=10):
        os.rename(p("root", src), p("root", dst))
        inotify.on_event(
            InotifyEvent(
                root_wd, Mask(InotifyConstants.IN_MOVED_FROM | InotifyConstants.IN_ISDIR), cookie, src.encode()
            )
        )
        inotify.on_event(
            InotifyEvent(root_wd, Mask(InotifyConstants.IN_MOVED_TO | InotifyConstants.IN_ISDIR), cookie, dst.encode())
        )

    inotify.on_event(InotifyEvent(leaf_wd, Mask(InotifyConstants.IN_CREATE), 0, b"final.txt"))
    (frm1, to1), (frm2, to2), leaf_ev = inotify.read_event(), inotify.read_event(), inotify.read_event()
    assert (frm1.path, to1.path) == (p("root", "dir_a").encode(), p("root", "dir_b").encode())
    assert (frm2.path, to2.path) == (p("root", "dir_b").encode(), p("root", "dir_c").encode())
    assert isinstance(leaf_ev, PathedInotifyEvent)
    assert leaf_ev.path == p("root", "dir_c", "sub", "leaf", "final.txt").encode()
    inotify.deactivate()


@pytest.mark.parametrize("parent_first", [True, False])
def test_tree_removal_lifecycle(p: P, *, parent_first: bool) -> None:
    mkdir(p("root", "parent", "child"), parents=True)
    inotify = create_inotify_watch(p("root").encode(), recursive=True)
    parent_wd = inotify._active_callbacks_by_path[p("root", "parent").encode()]  # noqa: SLF001
    child_wd = inotify._active_callbacks_by_path[p("root", "parent", "child").encode()]  # noqa: SLF001

    if parent_first:
        inotify._remove_watch_internally(parent_wd)  # noqa: SLF001
        assert inotify._resolve_path(child_wd) == p("root", "parent", "child").encode()  # noqa: SLF001
        inotify._remove_watch_internally(child_wd)  # noqa: SLF001
    else:
        inotify._remove_watch_internally(child_wd)  # noqa: SLF001
        inotify._remove_watch_internally(parent_wd)  # noqa: SLF001

    assert parent_wd not in inotify._nodes_by_wd  # noqa: SLF001
    assert child_wd not in inotify._nodes_by_wd  # noqa: SLF001
    inotify.deactivate()


def test_move_into_already_occupied_destination(p: P) -> None:
    mkdir(p("root", "src_dir"), parents=True)
    mkdir(p("root", "dst_dir", "sub"), parents=True)
    inotify = create_inotify_watch(p("root").encode(), recursive=True)
    src_wd = inotify._active_callbacks_by_path[p("root", "src_dir").encode()]  # noqa: SLF001
    old_dst_wd = inotify._active_callbacks_by_path[p("root", "dst_dir").encode()]  # noqa: SLF001

    assert inotify._move_watches(p("root", "src_dir").encode(), p("root", "dst_dir").encode())  # noqa: SLF001
    assert old_dst_wd not in inotify._nodes_by_wd  # noqa: SLF001
    assert inotify._active_callbacks_by_path[p("root", "dst_dir").encode()] == src_wd  # noqa: SLF001
    inotify.deactivate()


def test_tree_move_cycle_rejection(p: P) -> None:
    mkdir(p("root", "a", "b", "c"), parents=True)
    inotify = create_inotify_watch(p("root").encode(), recursive=True)
    a_path = p("root", "a").encode()
    c_path = p("root", "a", "b", "c").encode()
    # Moving ancestor 'a' into descendant 'c' must be rejected
    assert not inotify._move_watches(a_path, os.path.join(c_path, b"a"))  # noqa: SLF001
    assert inotify._find_node_by_path(a_path) is not None  # noqa: SLF001
    inotify.deactivate()


def test_tree_move_root(p: P) -> None:
    mkdir(p("root", "sub"), parents=True)
    inotify = create_inotify_watch(p("root").encode(), recursive=True)
    new_root = p("new_root").encode()
    assert inotify._move_watches(p("root").encode(), new_root)  # noqa: SLF001
    assert inotify.path == new_root
    inotify.deactivate()


def test_tree_intermediate_placeholder_and_pruning(p: P) -> None:
    mkdir(p("root", "a", "b"), parents=True)
    inotify = create_inotify_watch(p("root").encode(), recursive=False)
    # Root is watched, but 'a' and 'b' are not watched yet
    b_path = p("root", "a", "b").encode()
    # Insert node directly into b: creates placeholder for 'a' with wd=-1
    node_b = inotify._insert_node(b_path, WatchDescriptor(42))  # noqa: SLF001
    assert node_b is not None
    node_a = inotify._find_node_by_path(p("root", "a").encode())  # noqa: SLF001
    assert node_a is not None
    assert node_a.wd == WatchDescriptor(-1)  # Placeholder
    assert inotify._resolve_path(WatchDescriptor(42)) == b_path  # noqa: SLF001

    # Removing b should prune empty placeholder 'a'
    inotify._remove_watch_internally(WatchDescriptor(42))  # noqa: SLF001
    assert inotify._find_node_by_path(p("root", "a").encode()) is None  # noqa: SLF001
    inotify.deactivate()
