from functools import partial
import os
import pytest
from tests import shell


@pytest.fixture()
def tmpdir(request):
    path = os.path.realpath(shell.mkdtemp())
    def finalizer():
        shell.rm(path, recursive=True)
    request.addfinalizer(finalizer)
    return path


@pytest.fixture()
def p(tmpdir, *args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return partial(os.path.join, tmpdir)
