from typing import Any

import pytest
from watchdog.utils import echo


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (("x", (1, 2, 3)), "x=(1, 2, 3)"),
    ],
)
def test_format_arg_value(value: tuple[str, tuple[Any, ...]], expected: str) -> None:
    assert echo.format_arg_value(value) == expected
