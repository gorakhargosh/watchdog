from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

EXAMPLES_DIR = Path("docs/source/examples")
EXAMPLES = [str(p) for p in sorted(EXAMPLES_DIR.glob("*.py")) if p.name != "__init__.py"]


@pytest.mark.parametrize("script_path", EXAMPLES)
def test_example(script_path: str) -> None:
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
