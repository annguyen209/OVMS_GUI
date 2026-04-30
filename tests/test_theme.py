import re
import pytest
from app import theme

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')

_EXPECTED = [
    "BG", "CARD", "CARD2", "BORDER", "BORDER2",
    "TEXT", "TEXT2", "MUTED",
    "BLUE", "BLUE_H", "GREEN", "RED", "AMBER",
    "BANNER", "FOOTER", "GRAY",
    "CODE_BG", "CODE_FG",
    "USER_BG", "ASSIST_BG", "SYSTEM_BG", "CHAT_BG",
]

@pytest.mark.parametrize("name", _EXPECTED)
def test_constant_exists_and_is_hex(name):
    value = getattr(theme, name)
    assert _HEX.match(value), f"{name}={value!r} is not a valid hex color"
