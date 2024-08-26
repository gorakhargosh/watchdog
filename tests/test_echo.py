from typing import Any

from watchdog.utils import echo
import pytest


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (("x", (1, 2, 3)), "x=(1, 2, 3)"),
    ],
)
def test_format_arg_value(value: tuple[str, tuple[Any, ...]], expected: str) -> None:
    assert echo.format_arg_value(value) == expected
