"""Coverage for watchdog.utils.platform and the <3.13 compat shims."""

from __future__ import annotations

import sys
from pathlib import PurePosixPath, PureWindowsPath
from unittest import mock

import pytest

from watchdog.utils import backwards_compat, platform
from watchdog.utils.patterns import _full_match


@pytest.mark.parametrize(
    ("sys_platform", "uname_release", "expected"),
    [
        ("win32", "", platform.PLATFORM_WINDOWS),
        ("darwin", "", platform.PLATFORM_DARWIN),
        ("linux", "", platform.PLATFORM_LINUX),
        ("freebsd15", "15.0-RELEASE", platform.PLATFORM_LINUX),  # FreeBSD 15+ has inotify
        ("freebsd14", "14.2-RELEASE", platform.PLATFORM_BSD),
        ("netbsd", "", platform.PLATFORM_BSD),
        ("openbsd", "", platform.PLATFORM_BSD),
        ("dragonfly", "", platform.PLATFORM_BSD),
        ("sunos5", "", platform.PLATFORM_UNKNOWN),
    ],
)
def test_get_platform_name_branches(sys_platform, uname_release, expected):
    with mock.patch.object(sys, "platform", sys_platform), mock.patch("os.uname") as uname:
        uname.return_value.release = uname_release
        assert platform.get_platform_name() == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (platform.PLATFORM_LINUX, (True, False, False, False)),
        (platform.PLATFORM_BSD, (False, True, False, False)),
        (platform.PLATFORM_DARWIN, (False, False, True, False)),
        (platform.PLATFORM_WINDOWS, (False, False, False, True)),
        (platform.PLATFORM_UNKNOWN, (False, False, False, False)),
    ],
)
def test_platform_predicates(name, expected):
    with mock.patch.object(platform, "__platform__", name):
        assert platform.is_linux() == expected[0]
        assert platform.is_bsd() == expected[1]
        assert platform.is_darwin() == expected[2]
        assert platform.is_windows() == expected[3]


def test_backwards_compat_translate_matches_stdlib_glob():
    import glob as stdlib_glob

    for pattern in ["*.py", "src/**/*.py", "[a-c]?.txt", "no/match/**/x"]:
        ours = backwards_compat.translate(pattern, recursive=True, include_hidden=True, seps="/")
        theirs = stdlib_glob.translate(pattern, recursive=True, include_hidden=True, seps="/")
        assert ours == theirs, pattern


def test_backwards_compat_translate_without_seps():
    assert backwards_compat.translate("a?c") == r"(?s:a[^/]c)\Z"


def test_full_match_posix_path():
    assert _full_match(PurePosixPath("/tmp/x.py"), "**/*.py")
    assert not _full_match(PurePosixPath("/tmp/x.txt"), "**/*.py")


def test_full_match_windows_path_is_case_insensitive():
    assert _full_match(PureWindowsPath("C:\\Docs\\A.PY"), "**/*.py")


def test_full_match_falls_back_to_compat_translate_on_old_python():
    # Python < 3.13 has no PurePath.full_match; simulate it.
    with mock.patch.object(PurePosixPath, "full_match", side_effect=AttributeError):
        assert _full_match(PurePosixPath("/tmp/x.py"), "**/*.py")
        assert not _full_match(PurePosixPath("/tmp/x.txt"), "**/*.py")


def test_full_match_unsupported_path_type():
    from watchdog.utils.patterns import _get_sep

    assert _get_sep(PureWindowsPath("C:\\x")) == "\\"
    assert _get_sep(PurePosixPath("/x")) == "/"
    with pytest.raises(TypeError, match="Unsupported"):
        _get_sep(object())  # type: ignore[arg-type]
