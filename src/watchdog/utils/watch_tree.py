""":module: watchdog.utils.watch_tree
:synopsis: Generic descriptor-indexed directory tree for observer backends.
:author: Prateek Dagar (@prateek-dagar)
"""

from __future__ import annotations

import logging
import os
from typing import Generic, TypeVar, cast

logger = logging.getLogger(__name__)

DescriptorT = TypeVar("DescriptorT", bound=int)

INVALID_WATCH_DESCRIPTOR: int = -1


class DirNode(Generic[DescriptorT]):
    """N-ary directory tree node for hierarchical watch tracking."""

    __slots__ = ("children", "name", "parent", "wd")

    def __init__(
        self,
        name: bytes,
        wd: DescriptorT,
        parent: DirNode[DescriptorT] | None = None,
    ) -> None:
        self.name = name
        self.wd: DescriptorT = wd
        self.parent = parent
        self.children: dict[bytes, DirNode[DescriptorT]] = {}


class WatchTree(Generic[DescriptorT]):
    """Tree of watched directories indexed by OS watch/file descriptor.

    Shared by descriptor-based observer backends (e.g. ``inotify``, and future
    ``kqueue`` / ``fanotify`` optimizations). Paths are resolved by walking the
    tree up to its root, so moving a directory only re-parents its node instead
    of rewriting the path of every watch below it.
    """

    def __init__(
        self,
        root_path: bytes,
        *,
        invalid_wd: DescriptorT | None = None,
    ) -> None:
        self.root_path = root_path
        self._invalid_wd: DescriptorT = (
            cast("DescriptorT", INVALID_WATCH_DESCRIPTOR) if invalid_wd is None else invalid_wd
        )
        self.root: DirNode[DescriptorT] | None = None
        self.nodes_by_wd: dict[DescriptorT, DirNode[DescriptorT]] = {}

    def watch_descriptors(self) -> list[DescriptorT]:
        return list(self.nodes_by_wd)

    def find_node_by_path(self, path: bytes) -> DirNode[DescriptorT] | None:
        if self.root is None:
            return None
        norm_path = os.path.normpath(path)
        norm_root = os.path.normpath(self.root_path)
        if norm_path == norm_root:
            return self.root

        sep = os.path.sep.encode()
        if norm_root == sep:
            rel = norm_path[len(sep) :]
        else:
            prefix = norm_root + sep
            if not norm_path.startswith(prefix):
                return None
            rel = norm_path[len(prefix) :]

        parts = [p for p in rel.split(sep) if p]
        curr = self.root
        for part in parts:
            child = curr.children.get(part)
            if child is None:
                return None
            curr = child
        return curr

    def insert_node(self, path: bytes, wd: DescriptorT) -> DirNode[DescriptorT] | None:
        norm_path = os.path.normpath(path)
        norm_root = os.path.normpath(self.root_path)
        if norm_path == norm_root:
            if self.root is None:
                self.root = DirNode(name=b"", wd=wd, parent=None)
            else:
                self.root.wd = wd
            self.nodes_by_wd[wd] = self.root
            return self.root

        sep = os.path.sep.encode()
        if norm_root == sep:
            rel = norm_path[len(sep) :]
        else:
            prefix = norm_root + sep
            if not norm_path.startswith(prefix):
                logger.warning("Path %r is not under watched root %r", path, self.root_path)
                return None
            rel = norm_path[len(prefix) :]

        parts = [p for p in rel.split(sep) if p]
        if not parts:
            return self.root

        if self.root is None:
            self.root = DirNode(name=b"", wd=self._invalid_wd, parent=None)

        curr = self.root
        for part in parts[:-1]:
            child = curr.children.get(part)
            if child is None:
                child = DirNode(name=part, wd=self._invalid_wd, parent=curr)
                curr.children[part] = child
            curr = child

        last_part = parts[-1]
        existing = curr.children.get(last_part)
        if existing is not None:
            existing.wd = wd
            node = existing
        else:
            node = DirNode(name=last_part, wd=wd, parent=curr)
            curr.children[last_part] = node

        # Note on descriptor cardinality:
        # In Linux inotify, inotify_add_watch returns the same WatchDescriptor for multiple paths
        # that resolve to the same underlying inode (e.g. symlinks followed into an existing directory).
        # Both upstream flat dicts and this tree map wd -> most recently registered node.
        # TODO: Consider multi-node mapping per wd if symlink alias path disambiguation is required.
        self.nodes_by_wd[wd] = node
        return node

    def resolve_path(self, wd: DescriptorT) -> bytes | None:
        # TODO: Add bounded LRU/FIFO path cache if needed for high-frequency path resolution.
        node = self.nodes_by_wd.get(wd)
        if node is None:
            return None
        return self.path_of_node(node)

    def path_of_node(self, node: DirNode[DescriptorT]) -> bytes | None:
        """Return the full path of ``node``, or None if it is no longer attached to the tree."""
        if node is self.root:
            return self.root_path

        parts: list[bytes] = []
        curr: DirNode[DescriptorT] | None = node
        root = self.root
        while curr is not None and curr is not root:
            parent = curr.parent
            if parent is None or parent.children.get(curr.name) is not curr:
                return None
            parts.append(curr.name)
            curr = parent

        if curr is not root:
            return None

        parts.reverse()
        sep = os.path.sep.encode()
        root_path = self.root_path
        if root_path.endswith(sep):
            return root_path + sep.join(parts)
        return root_path + sep + sep.join(parts)

    def detach_deleted_directory(self, path: bytes) -> None:
        """Detach the node of a deleted directory from its parent.

        Downward lookups (find_node_by_path) then no longer resolve it, allowing a newly created
        directory at the same path to register independently. The old node's descriptor remains
        alive in nodes_by_wd until the backend removes it.
        """
        node = self.find_node_by_path(path)
        if node is None:
            return
        parent = node.parent
        if parent is not None and parent.children.get(node.name) is node:
            parent.children.pop(node.name, None)

    def prune_empty_ancestors(self, node: DirNode[DescriptorT]) -> None:
        curr: DirNode[DescriptorT] | None = node
        while curr is not None and curr is not self.root:
            if curr.children or curr.wd != self._invalid_wd:
                break
            parent = curr.parent
            if parent is not None and parent.children.get(curr.name) is curr:
                parent.children.pop(curr.name, None)
            curr.parent = None
            curr = parent
        if self.root is not None and not self.root.children and self.root.wd == self._invalid_wd:
            self.root = None

    def detach_subtree(self, node: DirNode[DescriptorT], path: bytes) -> tuple[list[bytes], list[DescriptorT]]:
        """Detach ``node`` and its descendants from the tree.

        Returns the paths of the detached descendants and the descriptors that
        are no longer tracked, so the caller can remove the matching kernel watches.
        """
        if node is self.root:
            return [], []

        if node.parent is not None and node.parent.children.get(node.name) is node:
            node.parent.children.pop(node.name, None)
        node.parent = None

        sub_paths: list[bytes] = []
        wds: list[DescriptorT] = []
        stack: list[tuple[DirNode[DescriptorT], bytes]] = [(node, path)]
        while stack:
            curr, curr_path = stack.pop()
            if curr is not node:
                sub_paths.append(curr_path)
            if curr.wd != self._invalid_wd:
                wds.append(curr.wd)
                self.nodes_by_wd.pop(curr.wd, None)
            for name, child in reversed(curr.children.items()):
                stack.append((child, os.path.join(curr_path, name)))
            curr.children.clear()
            curr.parent = None
        return sub_paths, wds

    def remove_wd(self, wd: DescriptorT) -> None:
        """Forget the descriptor ``wd`` and prune the nodes left without a watch or children."""
        node = self.nodes_by_wd.pop(wd, None)
        if node is not None:
            node.wd = self._invalid_wd
            if node is self.root and not node.children:
                self.root = None
            elif not node.children:
                self.prune_empty_ancestors(node)
