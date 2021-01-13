# coding: utf-8
#
# Copyright (C) 2010 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2020 Boris Staletic <boris.staletic@gmail.com>

import pytest
from watchdog.utils.patterns import _match_path, filter_paths, match_any_paths


@pytest.mark.parametrize("input, included_patterns, excluded_patterns, case_sensitive, expected", [
    ("/users/gorakhargosh/foobar.py", {"*.py"}, {"*.PY"}, True, True),
    ("/users/gorakhargosh/foobar.py", {"*.py"}, {"*.PY"}, True, True),
    ("/users/gorakhargosh/", {"*.py"}, {"*.txt"}, False, False),
    ("/users/gorakhargosh/foobar.py", {"*.py"}, {"*.PY"}, False, ValueError),
])
def test_match_path(input, included_patterns, excluded_patterns, case_sensitive, expected):
    if expected == ValueError:
        with pytest.raises(expected):
            _match_path(input, included_patterns, excluded_patterns, case_sensitive)
    else:
        assert _match_path(input, included_patterns, excluded_patterns, case_sensitive) is expected


@pytest.mark.parametrize("included_patterns, excluded_patterns, case_sensitive, expected", [
    (None, None, True, None),
    (None, None, False, None),
    (["*.py", "*.conf"], ["*.status"], True, {"/users/gorakhargosh/foobar.py", "/etc/pdnsd.conf"}),
])
def test_filter_paths(included_patterns, excluded_patterns, case_sensitive, expected):
    pathnames = {"/users/gorakhargosh/foobar.py", "/var/cache/pdnsd.status", "/etc/pdnsd.conf", "/usr/local/bin/python"}
    actual = set(filter_paths(pathnames, included_patterns, excluded_patterns, case_sensitive))
    assert actual == expected if expected else pathnames


@pytest.mark.parametrize("included_patterns, excluded_patterns, case_sensitive, expected", [
    (None, None, True, True),
    (None, None, False, True),
    (["*py", "*.conf"], ["*.status"], True, True),
    (["*.txt"], None, False, False),
    (["*.txt"], None, True, False),
])
def test_match_any_paths(included_patterns, excluded_patterns, case_sensitive, expected):
    pathnames = {"/users/gorakhargosh/foobar.py", "/var/cache/pdnsd.status", "/etc/pdnsd.conf", "/usr/local/bin/python"}
    assert match_any_paths(pathnames, included_patterns, excluded_patterns, case_sensitive) == expected
