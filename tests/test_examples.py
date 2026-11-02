from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

EXAMPLES_DIR = Path("docs/source/examples")
EXAMPLES = [str(p) for p in sorted(EXAMPLES_DIR.glob("*.py")) if p.name != "__init__.py"]
CONFIG_EXAMPLES = [str(p) for p in sorted(EXAMPLES_DIR.glob("*tricks*")) if p.suffix in {".yaml", ".yml", ".json"}]


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


@pytest.mark.parametrize("config_path", CONFIG_EXAMPLES)
def test_tricks_example(config_path: str) -> None:
    # Skip if import PyYAML failed. PyYAML missing possible because
    # watchdog installed without watchmedo. See Installation section.
    if config_path.endswith((".yaml", ".yml")):
        pytest.importorskip("yaml")

    from watchdog import watchmedo
    from watchdog.utils import WatchdogShutdownError

    args = watchmedo.cli.parse_args(["tricks-from", config_path])
    with patch("time.sleep", side_effect=WatchdogShutdownError):
        watchmedo.tricks_from(args)
