from __future__ import annotations

import importlib.util
import sys
from unittest.mock import patch

import pytest


def run_example_via_import(script_path: str) -> None:
    # Mock sys.argv to supply the path parameter, and time.sleep to exit the loop
    with patch("sys.argv", [script_path, "."]), patch("time.sleep", side_effect=KeyboardInterrupt):
        # Load and execute the module dynamically
        spec = importlib.util.spec_from_file_location("example_module", script_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        
        # This will run the script, trigger KeyboardInterrupt, and run the finally block
        with pytest.raises(KeyboardInterrupt):
            spec.loader.exec_module(module)


def test_simple_example():
    run_example_via_import("docs/source/examples/simple.py")


def test_patterns_example():
    run_example_via_import("docs/source/examples/patterns.py")


def test_logger_example():
    run_example_via_import("docs/source/examples/logger.py")
