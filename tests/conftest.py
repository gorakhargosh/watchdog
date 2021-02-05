from functools import partial
import gc
import os
import threading
import pytest
from . import shell


@pytest.fixture()
def tmpdir(request):
    path = os.path.realpath(shell.mkdtemp())
    yield path
    shell.rm(path, recursive=True)


@pytest.fixture()
def p(tmpdir, *args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return partial(os.path.join, tmpdir)


@pytest.fixture(autouse=True)
def no_thread_leaks():
    """
    Fail on thread leak.
    We do not use pytest-threadleak because it is not reliable.
    """
    old_thread_count = threading.active_count()
    yield
    gc.collect()  # Clear the stuff from other function-level fixtures
    assert threading.active_count() == old_thread_count  # Only previously existing threads


@pytest.fixture(autouse=True)
def no_warnings(recwarn):
    """Fail on warning."""

    yield

    warnings = []
    for warning in recwarn:  # pragma: no cover
        message = str(warning.message)
        filename = warning.filename
        if (
            "Not importing directory" in message
            or "Using or importing the ABCs" in message
            or "dns.hash module will be removed in future versions" in message
            or ("eventlet" in filename and "eventlet" in filename)
        ):
            continue
        warnings.append("{w.filename}:{w.lineno} {w.message}".format(w=warning))
    assert not warnings
