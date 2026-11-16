from __future__ import annotations

import ctypes
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from watchdog.utils.statx import (
    AT_FDCWD,
    AT_SYMLINK_NOFOLLOW,
    STATX_BTIME,
    _StructStatx,
    get_statx_birthtime_ns,
    is_statx_available,
)


def test_statx_abi() -> None:
    """Linux kernel struct statx size is 256 bytes for ABI stability."""
    assert ctypes.sizeof(_StructStatx) == 256
    assert isinstance(is_statx_available(), bool)


@pytest.mark.parametrize(
    ("available", "ret_code", "mask", "expected"),
    [
        (False, 0, STATX_BTIME, None),  # statx unavailable
        (True, 0, STATX_BTIME, 1_700_000_000_123_456_789),  # Success
        (True, 0, 0, None),  # Filesystem does not support birthtime (e.g. FAT, NFS)
        (True, -1, STATX_BTIME, None),  # Syscall error
    ],
)
def test_get_statx_birthtime_ns(available: Any, ret_code: int, mask: int, expected: int | None) -> None:
    def fake_statx(*args: Any) -> int:
        stx = args[4].contents
        stx.stx_mask = mask
        stx.stx_btime.tv_sec, stx.stx_btime.tv_nsec = 1_700_000_000, 123_456_789
        return ret_code

    mock_func = MagicMock(side_effect=fake_statx)
    with (
        patch("watchdog.utils.statx.is_statx_available", return_value=available),
        patch("watchdog.utils.statx.hasattr", return_value=False),
        patch("watchdog.utils.statx._statx_func", mock_func),
    ):
        assert get_statx_birthtime_ns("file", follow_symlinks=True) == expected
        if available and ret_code == 0 and mask == STATX_BTIME:
            assert mock_func.call_args[0][0] == AT_FDCWD
            assert mock_func.call_args[0][2] == 0
            assert mock_func.call_args[0][3] == STATX_BTIME

            # Verify symlink flag behavior
            get_statx_birthtime_ns("file", follow_symlinks=False)
            assert mock_func.call_args[0][2] == AT_SYMLINK_NOFOLLOW
