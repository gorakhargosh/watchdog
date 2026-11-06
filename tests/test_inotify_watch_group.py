from __future__ import annotations

import pytest

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

import os
import random
from typing import TYPE_CHECKING, cast

from watchdog.observers.inotify import InotifyWatchGroup
from watchdog.observers.inotify_c import WATCHDOG_ALL_EVENTS, InotifyConstants, InotifyEvent, InotifyFD, Mask
from watchdog.observers.inotify_move_event_grouper import GroupedInotifyEvent, PathedInotifyEvent

from .shell import mkdir, mount_tmpfs, mv, rm, symlink, touch, unmount

if TYPE_CHECKING:
    from collections.abc import Callable


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


class FakeKernelInotifyFD:
    """Stands in for InotifyFD with a fake kernel that hands out one descriptor per directory."""

    def __init__(self) -> None:
        self.kernel: dict[bytes, int] = {}
        self.masks: dict[bytes, Mask] = {}
        self.next_wd = 0
        self.added: list[bytes] = []
        self.added_masks: list[Mask] = []
        self.removed: list[tuple[int, object]] = []

    def watch_descriptor_for(self, path: bytes, mask: Mask) -> int:
        if not os.path.isdir(path):
            raise FileNotFoundError(path)
        if path not in self.kernel:
            self.next_wd += 1
            self.kernel[path] = self.next_wd
        self.masks[path] = mask  # inotify_add_watch replaces the mask of an existing watch
        return self.kernel[path]

    def add_callback(self, path: bytes, mask: Mask, callback: object, id_: object) -> int:
        self.added.append(path)
        self.added_masks.append(mask)
        return self.watch_descriptor_for(path, mask)

    def remove_callbacks(self, callbacks: list[tuple[int, object]]) -> None:
        self.removed.extend(callbacks)

    def forget(self, path: bytes) -> None:
        """The directory was deleted: the kernel dropped its watch."""
        del self.kernel[path]
        del self.masks[path]


def create_fake_kernel_watch(p, fake_fd: FakeKernelInotifyFD) -> InotifyWatchGroup:
    return InotifyWatchGroup(
        cast("InotifyFD", fake_fd), p("root").encode(), is_recursive=True, event_mask=WATCHDOG_ALL_EVENTS
    )


def test_queue_overflow_reconciles_recursive_watches_in_place(p, caplog):
    mkdir(p("root", "kept"), parents=True)
    mkdir(p("root", "gone"))
    fake_fd = FakeKernelInotifyFD()
    inotify = create_fake_kernel_watch(p, fake_fd)
    before = dict(inotify._active_callbacks_by_path)  # noqa: SLF001
    fake_fd.added.clear()
    fake_fd.added_masks.clear()
    mkdir(p("root", "missed", "child"), parents=True)
    rm(p("root", "gone"), recursive=True)
    fake_fd.forget(p("root", "gone").encode())

    inotify.on_queue_overflow()

    # Only the watch of the deleted directory is removed; the live ones are left alone.
    assert fake_fd.removed == [(before[p("root", "gone").encode()], inotify._id)]  # noqa: SLF001
    assert fake_fd.added == [p("root", "missed").encode(), p("root", "missed", "child").encode()]
    after = inotify._active_callbacks_by_path  # noqa: SLF001
    assert set(after) == {
        p("root").encode(),
        p("root", "kept").encode(),
        p("root", "missed").encode(),
        p("root", "missed", "child").encode(),
    }
    assert after[p("root").encode()] == before[p("root").encode()]
    assert after[p("root", "kept").encode()] == before[p("root", "kept").encode()]
    # New directories were watched quietly during the walk, and every watch ends with its full mask.
    assert all(not mask & InotifyConstants.IN_OPEN for mask in fake_fd.added_masks)
    assert all(fake_fd.masks[path] == inotify.event_mask for path in after)
    assert "reconciling recursive watches" in caplog.text
    inotify.deactivate()


def test_queue_overflow_replaces_the_watch_of_a_recreated_directory(p):
    mkdir(p("root", "dir"), parents=True)
    fake_fd = FakeKernelInotifyFD()
    inotify = create_fake_kernel_watch(p, fake_fd)
    old_wd = inotify._active_callbacks_by_path[p("root", "dir").encode()]  # noqa: SLF001
    # Deleted and created again while the events saying so were lost.
    rm(p("root", "dir"), recursive=True)
    fake_fd.forget(p("root", "dir").encode())
    mkdir(p("root", "dir"))

    inotify.on_queue_overflow()

    new_wd = inotify._active_callbacks_by_path[p("root", "dir").encode()]  # noqa: SLF001
    assert new_wd != old_wd
    assert fake_fd.removed == [(old_wd, inotify._id)]  # noqa: SLF001
    assert inotify._active_callbacks_by_watch[new_wd] == p("root", "dir").encode()  # noqa: SLF001
    assert old_wd not in inotify._active_callbacks_by_watch  # noqa: SLF001
    inotify.deactivate()


def test_queue_overflow_keeps_a_filtered_event_mask(p):
    mkdir(p("root", "dir"), parents=True)
    fake_fd = FakeKernelInotifyFD()
    filtered = Mask(InotifyConstants.IN_CREATE | InotifyConstants.IN_DELETE | InotifyConstants.IN_DELETE_SELF)
    inotify = InotifyWatchGroup(cast("InotifyFD", fake_fd), p("root").encode(), is_recursive=True, event_mask=filtered)
    mkdir(p("root", "missed"))

    inotify.on_queue_overflow()

    # Nothing to quiet, and no watch is widened to events the caller did not ask for.
    assert set(fake_fd.masks.values()) == {inotify.event_mask}
    assert inotify.event_mask & ~InotifyConstants.IN_DONT_FOLLOW == filtered
    assert p("root", "missed").encode() in inotify._active_callbacks_by_path  # noqa: SLF001
    inotify.deactivate()


def test_queue_overflow_survives_a_directory_deleted_during_the_reconcile(p):
    mkdir(p("root", "vanishing"), parents=True)
    vanishing = p("root", "vanishing").encode()

    class DeletingInotifyFD(FakeKernelInotifyFD):
        def add_callback(self, path: bytes, mask: Mask, callback: object, id_: object) -> int:
            wd = super().add_callback(path, mask, callback, id_)
            if path == p("root", "missed").encode() and vanishing in self.kernel:
                rm(p("root", "vanishing"), recursive=True)
                self.forget(vanishing)
            return wd

    fake_fd = DeletingInotifyFD()
    inotify = create_fake_kernel_watch(p, fake_fd)
    mkdir(p("root", "missed"))

    inotify.on_queue_overflow()

    # The deleted directory's own events remove its watch; every other watch gets its full mask back.
    assert set(fake_fd.masks) == {p("root").encode(), p("root", "missed").encode()}
    assert all(mask == inotify.event_mask for mask in fake_fd.masks.values())
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_queue_overflow_keeps_kernel_watches(p):
    # The reconcile must queue nothing itself, or on a tree with more directories than
    # fs.inotify.max_queued_events it overflows the queue it is recovering from. Removing a watch
    # queues IN_IGNORED, and reading a directory queues IN_OPEN, IN_ACCESS and IN_CLOSE_NOWRITE:
    # live watches keep their descriptors, and the first event after it is the next real change.
    for i in range(50):
        mkdir(p("root", f"dir{i}"), parents=True)
    inotify = create_inotify_watch(p("root").encode(), recursive=True)
    before = dict(inotify._active_callbacks_by_path)  # noqa: SLF001
    # Drain what registering the watches queued: that walk reads every directory too.
    touch(p("root", "dir3", "before"))
    while True:
        event = inotify.read_event()
        if (
            isinstance(event, PathedInotifyEvent)
            and event.path == p("root", "dir3", "before").encode()
            and event.ev.is_close_write
        ):
            break

    inotify.on_queue_overflow()

    assert inotify._active_callbacks_by_path == before  # noqa: SLF001
    touch(p("root", "dir7", "after"))
    assert_event(inotify, p("root", "dir7", "after"), InotifyConstants.IN_CREATE)
    inotify.deactivate()
