from __future__ import annotations

import errno
import os
import pickle
import stat
import time
from unittest.mock import patch

import pytest

from watchdog.utils import platform
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff, EmptyDirectorySnapshot

from .shell import chmod, mkdir, mv, rm, symlink, touch


def wait():
    """
    Wait long enough for file/folder mtime to change. This is needed
    to be able to detected modifications.
    """
    if platform.is_darwin() or platform.is_windows():
        # on macOS resolution of stat.mtime is only 1 second
        time.sleep(1.5)
    else:
        time.sleep(0.5)


def test_pickle(p):
    """It should be possible to pickle a snapshot."""
    mkdir(p("dir1"))
    snasphot = DirectorySnapshot(p("dir1"))
    pickle.dumps(snasphot)


def test_move_to(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))
    ref = DirectorySnapshot(p("dir2"))
    mv(p("dir1", "a"), p("dir2", "b"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("dir2")))
    assert diff.files_created == [p("dir2", "b")]


def test_move_to_with_context_manager(p):
    mkdir(p("dir1"))
    touch(p("dir1", "a"))
    mkdir(p("dir2"))

    dir1_cm = DirectorySnapshotDiff.ContextManager(p("dir1"))
    dir2_cm = DirectorySnapshotDiff.ContextManager(p("dir2"))
    with dir1_cm, dir2_cm:
        mv(p("dir1", "a"), p("dir2", "b"))

    assert dir1_cm.diff.files_deleted == [p("dir1", "a")]
    assert dir2_cm.diff.files_created == [p("dir2", "b")]


def test_move_from(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))
    ref = DirectorySnapshot(p("dir1"))
    mv(p("dir1", "a"), p("dir2", "b"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("dir1")))
    assert diff.files_deleted == [p("dir1", "a")]


def test_move_internal(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))
    ref = DirectorySnapshot(p(""))
    mv(p("dir1", "a"), p("dir2", "b"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("")))
    assert diff.files_moved == [(p("dir1", "a"), p("dir2", "b"))]
    assert diff.files_created == []
    assert diff.files_deleted == []


def test_move_replace(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))
    touch(p("dir2", "b"))
    ref = DirectorySnapshot(p(""))
    mv(p("dir1", "a"), p("dir2", "b"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("")))
    assert diff.files_moved == [(p("dir1", "a"), p("dir2", "b"))]
    assert diff.files_deleted == [p("dir2", "b")]
    assert diff.files_created == []


@pytest.mark.skipif(platform.is_windows(), reason="Creating symlinks requires privileges on Windows.")
def test_create_symlink_to_existing_file(p):
    # A new symlink shares its target's inode (the default stat follows symlinks),
    # so it must not be mistaken for a move of the still-present target. See #1110.
    mkdir(p("dir"))
    touch(p("dir", "a"))
    ref = DirectorySnapshot(p(""))
    symlink("a", p("dir", "a.link"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("")))
    assert diff.files_created == [p("dir", "a.link")]
    assert diff.files_moved == []
    assert diff.files_deleted == []


@pytest.mark.skipif(platform.is_windows(), reason="Creating symlinks requires privileges on Windows.")
def test_delete_symlink_to_existing_file(p):
    # Removing a symlink whose target remains must be reported as a deletion, not
    # a move onto the target that keeps the shared inode. See #1110.
    mkdir(p("dir"))
    touch(p("dir", "a"))
    symlink("a", p("dir", "a.link"))
    ref = DirectorySnapshot(p(""))
    rm(p("dir", "a.link"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("")))
    assert diff.files_deleted == [p("dir", "a.link")]
    assert diff.files_moved == []
    assert diff.files_created == []


def test_dir_modify_on_create(p):
    ref = DirectorySnapshot(p(""))
    wait()
    touch(p("a"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("")))
    assert diff.dirs_modified == [p("")]


def test_dir_modify_on_move(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))
    ref = DirectorySnapshot(p(""))
    wait()
    mv(p("dir1", "a"), p("dir2", "b"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("")))
    assert set(diff.dirs_modified) == {p("dir1"), p("dir2")}


def test_detect_modify_for_moved_files(p):
    touch(p("a"))
    ref = DirectorySnapshot(p(""))
    wait()
    touch(p("a"))
    mv(p("a"), p("b"))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p("")))
    assert diff.files_moved == [(p("a"), p("b"))]
    assert diff.files_modified == [p("a")]


def test_replace_dir_with_file(p):
    # Replace a dir with a file of the same name just before the normal listdir
    # call and ensure it doesn't cause an exception

    def listdir_fcn(path):
        if path == p("root", "dir"):
            rm(path, recursive=True)
            touch(path)
        return os.scandir(path)

    mkdir(p("root"))
    mkdir(p("root", "dir"))

    # Should NOT raise an OSError (ENOTDIR)
    DirectorySnapshot(p("root"), listdir=listdir_fcn)


def test_permission_error(p):
    # Test that unreadable folders are not raising exceptions
    mkdir(p("a", "b", "c"), parents=True)

    ref = DirectorySnapshot(p(""))
    walk_orig = DirectorySnapshot.walk

    def walk(self, root):
        """Generate a permission error on folder "a/b"."""
        # Generate the permission error
        if root.startswith(p("a", "b")):
            raise OSError(errno.EACCES, os.strerror(errno.EACCES))

        # Mimic the original method
        yield from walk_orig(self, root)

    with patch.object(DirectorySnapshot, "walk", new=walk):
        # Should NOT raise an OSError (EACCES)
        new_snapshot = DirectorySnapshot(p(""))

    diff = DirectorySnapshotDiff(ref, new_snapshot)
    assert repr(diff)
    assert len(diff) == 1

    # Children of a/b/ are no more accessible and so removed in the new snapshot
    assert diff.dirs_deleted == [(p("a", "b", "c"))]


def test_ignore_device(p):
    # Create a file and take a snapshot.
    touch(p("file"))
    ref = DirectorySnapshot(p(""))
    wait()

    inode_orig = DirectorySnapshot.inode

    inode_times = 0

    def inode(self, path):
        # This function will always return a different device_id,
        # even for the same file.
        nonlocal inode_times
        result = inode_orig(self, path)
        inode_times += 1
        return result[0], result[1] + inode_times

    # Set the custom inode function.
    with patch.object(DirectorySnapshot, "inode", new=inode):
        # If we make the diff of the same directory, since by default the
        # DirectorySnapshotDiff compares the snapshots using the device_id (and it will
        # be different), it thinks that the same file has been deleted and created again.
        snapshot = DirectorySnapshot(p(""))
        diff_with_device = DirectorySnapshotDiff(ref, snapshot)
        assert diff_with_device.files_deleted == [(p("file"))]
        assert diff_with_device.files_created == [(p("file"))]

        # Otherwise, if we choose to ignore the device, the file will not be detected as
        # deleted and re-created.
        snapshot = DirectorySnapshot(p(""))
        diff_without_device = DirectorySnapshotDiff(ref, snapshot, ignore_device=True)
        assert not len(diff_without_device)
        assert diff_without_device.files_deleted == []
        assert diff_without_device.files_created == []


def stat_with_changed_device(path):
    # Change the device ID while preserving the fields used by DirectorySnapshot.
    stat = os.stat(path)
    values = list(stat)
    values[2] += 1
    return os.stat_result(values, {"st_atime": stat.st_atime, "st_mtime": stat.st_mtime, "st_ctime": stat.st_ctime})


@pytest.mark.parametrize("is_directory", [False, True])
@pytest.mark.parametrize("modified", [False, True])
@pytest.mark.parametrize("ignore_device", [False, True])
def test_move_with_changed_device(p, is_directory, modified, ignore_device):
    source = p("before")
    destination = p("after")
    if is_directory:
        mkdir(source)
    else:
        touch(source)
    os.utime(source, (1000, 1000))
    ref = DirectorySnapshot(p(""))
    mv(source, destination)
    os.utime(destination, (1000, 1010 if modified else 1000))

    snapshot = DirectorySnapshot(p(""), stat=stat_with_changed_device)
    diff = DirectorySnapshotDiff(ref, snapshot, ignore_device=ignore_device)
    kind = "dirs" if is_directory else "files"
    if ignore_device:
        assert getattr(diff, f"{kind}_moved") == [(source, destination)]
        assert getattr(diff, f"{kind}_deleted") == []
        assert getattr(diff, f"{kind}_created") == []
        assert (source in getattr(diff, f"{kind}_modified")) == modified
    else:
        assert getattr(diff, f"{kind}_moved") == []
        assert source in getattr(diff, f"{kind}_deleted")
        assert destination in getattr(diff, f"{kind}_created")


def test_ignore_device_preserves_hard_link_moves(p):
    touch(p("a"))
    try:
        os.link(p("a"), p("b"))
    except OSError as e:
        pytest.skip(f"Hard links are unavailable: {e}")

    def listdir(path):
        with os.scandir(path) as entries:
            yield from sorted(entries, key=lambda entry: entry.name)

    ref = DirectorySnapshot(p(""))
    mv(p("a"), p("c"))
    snapshot = DirectorySnapshot(p(""), listdir=listdir)
    expected = DirectorySnapshotDiff(ref, snapshot)
    changed = DirectorySnapshot(p(""), stat=stat_with_changed_device, listdir=listdir)
    diff = DirectorySnapshotDiff(ref, changed, ignore_device=True)
    assert set(diff.files_moved) == set(expected.files_moved)
    assert diff.files_created == expected.files_created
    assert diff.files_deleted == expected.files_deleted


@pytest.mark.parametrize("ignore_device", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_empty_snapshot(p, ignore_device, reverse):
    # Create a file and declare a DirectorySnapshot and a EmptyDirectorySnapshot.
    # When we make the diff, although both objects were declared with the same items on
    # the directory, the file and directories created BEFORE the DirectorySnapshot will
    # be detected as newly created.

    touch(p("a"))
    mkdir(p("b", "c"), parents=True)
    ref = DirectorySnapshot(p(""))
    empty = EmptyDirectorySnapshot()
    assert repr(empty) == "{}"

    diff = (
        DirectorySnapshotDiff(ref, empty, ignore_device=ignore_device)
        if reverse
        else DirectorySnapshotDiff(empty, ref, ignore_device=ignore_device)
    )
    assert len(diff) == 4
    kind = "deleted" if reverse else "created"
    assert getattr(diff, f"files_{kind}") == [p("a")]
    assert sorted(getattr(diff, f"dirs_{kind}")) == sorted([p(""), p("b"), p("b", "c")])


def test_attrib_on_chmod(p):
    touch(p("a"))
    mkdir(p("dir1"))
    ref = DirectorySnapshot(p(""))
    mode = stat.S_IREAD if platform.is_windows() else 0o777
    chmod(p("a"), mode)
    chmod(p("dir1"), mode)
    new_snapshot = DirectorySnapshot(p(""))
    diff = DirectorySnapshotDiff(ref, new_snapshot)
    try:
        assert diff.files_attrib == [p("a")]
        assert diff.dirs_attrib == [p("dir1")]
        assert diff.files_modified == []
        assert diff.dirs_modified == []
        assert new_snapshot.mode(p("a")) == os.stat(p("a")).st_mode
    finally:
        chmod(p("a"), stat.S_IWRITE if platform.is_windows() else 0o644)
        chmod(p("dir1"), stat.S_IWRITE if platform.is_windows() else 0o755)
