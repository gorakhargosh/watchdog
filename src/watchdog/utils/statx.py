"""Linux statx(2) system call bindings for file birth time retrieval.

Standard POSIX struct stat on Linux does not include file birth time (unlike
st_birthtime on macOS/BSD or st_ctime on Windows). Linux kernel 4.11 introduced
the statx(2) system call which exposes stx_btime (birth time) on filesystems
that support it (ext4, Btrfs, XFS, etc.).

References:
- Linux manual page for statx(2): https://man7.org/linux/man-pages/man2/statx.2.html
- Linux kernel filesystem statx documentation: https://docs.kernel.org/filesystems/statx.html
- CPython Issue #83714 (statx integration): https://github.com/python/cpython/issues/83714
"""

from __future__ import annotations

import ctypes
import os
from typing import TYPE_CHECKING

from watchdog.utils import platform

if TYPE_CHECKING:
    from typing import Any

# Linux statx flags and mask constants (from linux/stat.h and linux/fcntl.h)
# AT_FDCWD: Interpret path relative to current working directory (like lstat).
AT_FDCWD = -100
# AT_SYMLINK_NOFOLLOW: Do not follow symlinks, inspecting the symlink itself (matching lstat).
AT_SYMLINK_NOFOLLOW = 0x100
# STATX_BTIME: Request file creation time (btime / birth time).
STATX_BTIME = 0x00000800
STATX_BASIC_STATS = 0x000007FF


class _StatxTimestamp(ctypes.Structure):
    _fields_ = [
        ("tv_sec", ctypes.c_int64),
        ("tv_nsec", ctypes.c_uint32),
        ("__reserved", ctypes.c_int32),
    ]


class _StructStatx(ctypes.Structure):
    _fields_ = [
        ("stx_mask", ctypes.c_uint32),
        ("stx_blksize", ctypes.c_uint32),
        ("stx_attributes", ctypes.c_uint64),
        ("stx_nlink", ctypes.c_uint32),
        ("stx_uid", ctypes.c_uint32),
        ("stx_gid", ctypes.c_uint32),
        ("stx_mode", ctypes.c_uint16),
        ("__spare0", ctypes.c_uint16 * 1),
        ("stx_ino", ctypes.c_uint64),
        ("stx_size", ctypes.c_uint64),
        ("stx_blocks", ctypes.c_uint64),
        ("stx_attributes_mask", ctypes.c_uint64),
        ("stx_atime", _StatxTimestamp),
        ("stx_btime", _StatxTimestamp),
        ("stx_ctime", _StatxTimestamp),
        ("stx_mtime", _StatxTimestamp),
        ("stx_rdev_major", ctypes.c_uint32),
        ("stx_rdev_minor", ctypes.c_uint32),
        ("stx_dev_major", ctypes.c_uint32),
        ("stx_dev_minor", ctypes.c_uint32),
        ("stx_mnt_id", ctypes.c_uint64),
        ("stx_dio_mem_align", ctypes.c_uint32),
        ("stx_dio_offset_align", ctypes.c_uint32),
        ("__spare2", ctypes.c_uint64 * 12),
    ]


_statx_available: bool | None = None
_statx_func: Any = None


def is_statx_available() -> bool:
    """Check if the Linux statx(2) system call is supported by the kernel and libc.

    statx(2) requires Linux kernel >= 4.11 and glibc >= 2.28 (e.g. Ubuntu 18.04+,
    Debian 10+, RHEL/CentOS 8+, Fedora 29+). On non-Linux platforms or older systems
    where the symbol is absent, this safely returns False.
    """
    global _statx_available, _statx_func
    if _statx_available is not None:
        return _statx_available

    if not platform.is_linux():
        _statx_available = False
        return False

    # Python 3.15+ provides native os.statx (CPython Issue #83714)
    if hasattr(os, "statx"):
        _statx_available = True
        return True

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if hasattr(libc, "statx"):
            _statx_func = libc.statx
            _statx_func.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_uint,
                ctypes.POINTER(_StructStatx),
            ]
            _statx_func.restype = ctypes.c_int
            _statx_available = True
        else:
            _statx_available = False
    except Exception:
        _statx_available = False

    return _statx_available


def get_statx_birthtime_ns(path: str | bytes, *, follow_symlinks: bool = True) -> int | None:
    """Retrieve file birth time (creation time) in nanoseconds using Linux statx(2).

    Returns None if statx is not supported by the kernel, libc, or underlying filesystem.
    Filesystems like ext4, Btrfs, and XFS support birth time. On filesystems that do not
    (e.g. FAT, NFSv3), statx succeeds with returncode 0 but leaves the STATX_BTIME bit
    unset in stx_mask; in that case, None is returned.

    :param path: File path to inspect.
    :param follow_symlinks: If True (default), inspects the target of symbolic links (matching os.stat).
                            If False, inspects the link itself without following (matching os.lstat).
    """
    if not is_statx_available():
        return None

    # TODO: Python 3.15+ adds os.statx() natively (https://github.com/python/cpython/issues/83714).
    # When Python < 3.15 support is dropped in watchdog, the ctypes wrapper below can be removed.
    if hasattr(os, "statx"):
        try:
            mask = getattr(os, "STATX_BTIME", STATX_BTIME)
            stx = os.statx(path, mask, follow_symlinks=follow_symlinks)
            btime_ns = getattr(stx, "stx_btime_ns", None) or getattr(stx, "st_birthtime_ns", None)
            if btime_ns is not None:
                return int(btime_ns)
            btime_sec = getattr(stx, "stx_btime", None) or getattr(stx, "st_birthtime", None)
            if btime_sec is not None:
                return int(btime_sec * 1_000_000_000)
        except Exception:
            return None

    if _statx_func is None:
        return None

    path_bytes = os.fsencode(path)
    stx = _StructStatx()
    flags = 0 if follow_symlinks else AT_SYMLINK_NOFOLLOW
    ret = _statx_func(AT_FDCWD, path_bytes, flags, STATX_BTIME, ctypes.pointer(stx))
    # Only return birth time if the call succeeded AND the filesystem filled STATX_BTIME.
    if ret == 0 and (stx.stx_mask & STATX_BTIME):
        return int(stx.stx_btime.tv_sec) * 1_000_000_000 + int(stx.stx_btime.tv_nsec)
    return None


def get_path_birthtime_ns(
    path: str | bytes,
    st: os.stat_result | None = None,
    *,
    follow_symlinks: bool = True,
) -> int | None:
    """Retrieve file birth time (creation time) in nanoseconds across platforms.

    Supports macOS/BSD (``st_birthtime_ns`` / ``st_birthtime``), Linux (``statx(2)``
    via :func:`get_statx_birthtime_ns`), and Windows (``st_birthtime`` / ``st_ctime``).
    If ``st`` is provided, inspects it first before falling back to statx or os.stat.
    Returns ``None`` if birth time is not supported by the OS or filesystem.

    :param path: File path string or bytes to inspect.
    :param st: Optional pre-queried :class:`os.stat_result` to inspect first.
    :param follow_symlinks: Whether to follow symbolic links.
    """
    decoded = os.fsdecode(path) if isinstance(path, bytes) else path
    if st is None and platform.is_linux():
        # Linux os.stat_result lacks st_birthtime; query statx(2) directly to avoid a redundant stat() syscall.
        return get_statx_birthtime_ns(decoded, follow_symlinks=follow_symlinks)

    if st is None:
        try:
            st = os.stat(decoded) if follow_symlinks else os.lstat(decoded)
        except OSError:
            st = None

    if st is not None:
        if (btime_ns := getattr(st, "st_birthtime_ns", None)) is not None:
            return int(btime_ns)
        if (btime_sec := getattr(st, "st_birthtime", None)) is not None:
            return int(btime_sec * 1_000_000_000)
        # On Windows, os.stat().st_ctime represents file creation time
        if platform.is_windows():
            if (ctime_ns := getattr(st, "st_ctime_ns", None)) is not None:
                return int(ctime_ns)
            if (ctime_sec := getattr(st, "st_ctime", None)) is not None:
                return int(ctime_sec * 1_000_000_000)

    return get_statx_birthtime_ns(decoded, follow_symlinks=follow_symlinks)
