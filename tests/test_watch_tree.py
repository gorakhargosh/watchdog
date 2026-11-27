from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from watchdog.utils.watch_tree import INVALID_WATCH_DESCRIPTOR, WatchTree

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def watch_root(tmp_path: Path) -> bytes:
    return os.fsencode(tmp_path / "watched")


def test_tree_lookup_and_move(watch_root: bytes, tmp_path: Path) -> None:
    tree: WatchTree[int] = WatchTree(watch_root)
    root_node = tree.insert_node(watch_root, 1)
    src = os.path.join(watch_root, b"src")
    leaf_path = os.path.join(src, b"sub", b"leaf")
    tree.insert_node(src, 2)
    leaf = tree.insert_node(leaf_path, 3)

    assert root_node is not None
    assert leaf is not None
    assert tree.find_node_by_path(os.path.join(src, b"sub")).wd == INVALID_WATCH_DESCRIPTOR  # type: ignore[union-attr]
    assert tree.resolve_path(3) == leaf_path
    assert tree.insert_node(os.fsencode(tmp_path / "outside"), 4) is None

    # O(1) directory move by re-parenting a single node.
    assert tree.root is not None
    node = tree.root.children.pop(b"src")
    node.name = b"dst"
    tree.root.children[b"dst"] = node
    assert tree.resolve_path(3) == os.path.join(watch_root, b"dst", b"sub", b"leaf")


@pytest.mark.parametrize("op", ["subtree", "remove_wd", "deleted_dir"])
def test_tree_detach(watch_root: bytes, op: str) -> None:
    tree: WatchTree[int] = WatchTree(watch_root)
    tree.insert_node(watch_root, 1)
    a_path = os.path.join(watch_root, b"a")
    a_node = tree.insert_node(a_path, 2)
    nested = os.path.join(a_path, b"nested")
    tree.insert_node(nested, 3)
    tree.insert_node(os.path.join(watch_root, b"b", b"deep"), 4)
    assert a_node is not None

    if op == "subtree":
        sub_paths, wds = tree.detach_subtree(a_node, a_path)
        assert sub_paths == [nested]
        assert set(wds) == {2, 3}
        assert tree.resolve_path(2) is None
    elif op == "remove_wd":
        tree.remove_wd(4)
        assert tree.find_node_by_path(os.path.join(watch_root, b"b")) is None
    else:
        tree.detach_deleted_directory(a_path)
        assert tree.path_of_node(a_node) is None
        new_node = tree.insert_node(a_path, 5)
        assert new_node is not None
        assert new_node is not a_node
        assert tree.resolve_path(5) == a_path
