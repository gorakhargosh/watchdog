from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

EXAMPLES_DIR = Path("docs/source/examples")
EXAMPLES = [str(p) for p in sorted(EXAMPLES_DIR.glob("*.py")) if p.name != "__init__.py"]


@pytest.mark.parametrize("script_path", EXAMPLES)
def test_example(script_path: str) -> None:
    # Mock sys.argv to supply the path parameter, and time.sleep to exit the loop
    with (
        patch("sys.argv", [script_path, "."]),
        patch("time.sleep", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        runpy.run_path(script_path, run_name="__main__")
