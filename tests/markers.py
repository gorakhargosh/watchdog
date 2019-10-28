from platform import python_implementation
import pytest


cpython_only = pytest.mark.skipif(python_implementation() != "CPython", reason="CPython only.")
