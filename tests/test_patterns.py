from __future__ import annotations

import glob

import pytest

from watchdog.utils import platform
from watchdog.utils.patterns import _match_path, filter_paths, match_any_paths


@pytest.mark.parametrize(
    ("raw_path", "included_patterns", "excluded_patterns", "case_sensitive", "base_path", "expected"),
    [
        ("/users/gorakhargosh/foobar.py", {"**/*.py"}, {"**/*.PY"}, True, None, True),
        ("/users/gorakhargosh/foobar.py", {"*.py"}, {"*.PY"}, True, None, False),
        ("/users/gorakhargosh/", {"*.py"}, {"*.txt"}, False, None, False),
        ("/users/gorakhargosh/foobar.py", {"*.py"}, {"*.PY"}, False, None, ValueError),
        # Relative matching with base_path
        ("/users/gorakhargosh/foobar.py", {"*.py"}, set(), True, "/users/gorakhargosh", True),
        ("/users/gorakhargosh/foobar.py", {"foobar.py"}, set(), True, "/users/gorakhargosh", True),
        ("/users/gorakhargosh/sub/foobar.py", {"*.py"}, set(), True, "/users/gorakhargosh", False),
        ("/users/gorakhargosh/sub/foobar.py", {"sub/*.py"}, set(), True, "/users/gorakhargosh", True),
        ("/users/gorakhargosh/sub/foobar.py", {"**/*.py"}, set(), True, "/users/gorakhargosh", True),
        ("/users/gorakhargosh/foobar.pyc", {"*.py"}, {"*.pyc"}, True, "/users/gorakhargosh", False),
        # Character classes (e.g. [0-9])
        ("/users/gorakhargosh/file3.py", {"**/file[0-9].py"}, set(), True, None, True),
        ("/users/gorakhargosh/filea.py", {"**/file[0-9].py"}, set(), True, None, False),
        # Literal brackets escaped using standard glob/fnmatch [[] syntax (see #991)
        ("/users/gorakhargosh/[test].txt", {"**/[[]test].txt"}, set(), True, None, True),
        ("/users/gorakhargosh/t.txt", {"**/[[]test].txt"}, set(), True, None, False),
        # Literal brackets escaped using glob.escape()
        ("/users/gorakhargosh/[test].txt", {f"**/{glob.escape('[test].txt')}"}, set(), True, None, True),
        # Complex adjacent/nested brackets escaped using glob.escape()
        ("/users/gorakhargosh/[[file]][][].txt", {f"**/{glob.escape('[[file]][][].txt')}"}, set(), True, None, True),
    ],
)
def test_match_path(
    raw_path: str,
    included_patterns: set[str],
    excluded_patterns: set[str],
    *,
    case_sensitive: bool,
    base_path: str | None,
    expected: bool | type[ValueError],
) -> None:
    if expected is ValueError:
        with pytest.raises(expected):
            _match_path(
                raw_path,
                included_patterns,
                excluded_patterns,
                case_sensitive=case_sensitive,
                base_path=base_path,
            )
    else:
        assert (
            _match_path(
                raw_path,
                included_patterns,
                excluded_patterns,
                case_sensitive=case_sensitive,
                base_path=base_path,
            )
            is expected
        )


@pytest.mark.parametrize(
    ("included_patterns", "excluded_patterns", "case_sensitive", "expected"),
    [
        (None, None, True, None),
        (None, None, False, None),
        (
            ["**/*.py", "**/*.conf"],
            ["**/*.status"],
            True,
            {"/users/gorakhargosh/foobar.py", "/etc/pdnsd.conf"},
        ),
    ],
)
def test_filter_paths(included_patterns, excluded_patterns, case_sensitive, expected):
    pathnames = {
        "/users/gorakhargosh/foobar.py",
        "/var/cache/pdnsd.status",
        "/etc/pdnsd.conf",
        "/usr/local/bin/python",
    }
    actual = set(
        filter_paths(
            pathnames,
            included_patterns=included_patterns,
            excluded_patterns=excluded_patterns,
            case_sensitive=case_sensitive,
        )
    )
    assert actual == expected if expected else pathnames


@pytest.mark.parametrize(
    ("included_patterns", "excluded_patterns", "case_sensitive", "expected"),
    [
        (None, None, True, True),
        (None, None, False, True),
        (["**/*py", "**/*.conf"], ["**/*.status"], True, True),
        (["**/*.txt"], None, False, False),
        (["**/*.txt"], None, True, False),
    ],
)
def test_match_any_paths(included_patterns, excluded_patterns, case_sensitive, expected):
    pathnames = {
        "/users/gorakhargosh/foobar.py",
        "/var/cache/pdnsd.status",
        "/etc/pdnsd.conf",
        "/usr/local/bin/python",
    }
    assert (
        match_any_paths(
            pathnames,
            included_patterns=included_patterns,
            excluded_patterns=excluded_patterns,
            case_sensitive=case_sensitive,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("raw_path", "pattern", "case_sensitive", "expected"),
    [
        ("/users/gorakhargosh/FOOBAR.PY", "**/*.py", False, True),
        ("/users/gorakhargosh/foobar.py", "**/*.PY", False, True),
        ("/users/gorakhargosh/FOOBAR.PY", "**/*.py", True, False),
        ("/users/gorakhargosh/foobar.py", "**/*.PY", True, False),
    ],
)
def test_match_path_case_sensitivity(raw_path, pattern, case_sensitive, expected):
    assert _match_path(raw_path, {pattern}, set(), case_sensitive=case_sensitive) is expected


@pytest.mark.skipif(not platform.is_windows(), reason="Native Windows path separators")
@pytest.mark.parametrize(
    ("raw_path", "included_patterns", "excluded_patterns", "base_path", "expected"),
    [
        (r"H:\root\sub\Report.TXT", {"sub/*.TXT"}, set(), r"H:\root", True),
        (r"H:\root\sub\Report.TXT", {r"sub\*.TXT"}, set(), r"H:\root", True),
        (r"H:\root\sub\Report.TXT", {"sub/*.TXT"}, set(), "H:/root", True),
        ("H:/root/sub/Report.TXT", {r"sub\*.TXT"}, set(), r"H:\root", True),
        (r"\\server\share\root\sub\Report.TXT", {"sub/*.TXT"}, set(), r"\\server\share\root", True),
        (r"H:\root\sub\Report.TXT", {"**/Report.TXT"}, set(), None, True),
        (r"H:\root\sub\Report.TXT", {r"H:\root\sub\*.TXT"}, set(), None, True),
        (r"H:\root\sub\Report.TXT", {"**"}, {"sub/*.TXT"}, r"H:\root", False),
        (r"H:\root\sub\Report.TXT", {"**"}, {r"sub\*.TXT"}, r"H:\root", False),
        (r"H:\root\sub\Report.TXT", {"**/*.txt"}, set(), None, False),
        (r"H:\root\sub\Report.TXT", {"Sub/*.TXT"}, set(), r"H:\root", False),
        (r"H:\other\sub\Report.TXT", {"sub/*.TXT"}, set(), r"H:\root", False),
    ],
)
def test_match_native_windows_paths(raw_path, included_patterns, excluded_patterns, base_path, expected) -> None:
    assert (
        _match_path(raw_path, included_patterns, excluded_patterns, case_sensitive=True, base_path=base_path)
        is expected
    )


@pytest.mark.skipif(not platform.is_windows(), reason="Native Windows path separators")
def test_filter_native_windows_paths_preserves_input() -> None:
    paths = [r"H:\root\sub\Report.TXT", r"H:\root\sub\Report.txt"]
    assert list(filter_paths(paths, included_patterns=[r"sub\*.TXT"], base_path=r"H:\root")) == paths[:1]


@pytest.mark.skipif(platform.is_windows(), reason="Backslashes are literal filename characters on POSIX")
def test_match_path_preserves_literal_backslashes() -> None:
    assert _match_path(r"sub\Report.TXT", {"*.TXT"}, set(), case_sensitive=True)
    assert not _match_path(r"sub\Report.TXT", {"sub/*.TXT"}, set(), case_sensitive=True)
