"""Tests for directory naming utilities."""

import pytest
from datetime import datetime, timezone
from . import format_dirname, parse_dirname

TIMESTAMP = datetime(2025, 8, 7, 15, 30, 45, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "git_info,suffix,expected",
    [
        ({"commit": "abc12345", "dirty": False}, "", "2025-08-07_153045_abc12345"),
        ({"commit": "def45678", "dirty": True}, "", "2025-08-07_153045_def45678-dirty"),
        (
            {"commit": "abc12345", "dirty": False},
            "exp_v2",
            "2025-08-07_153045_abc12345_exp_v2",
        ),
        (
            {"commit": "abc12345", "dirty": True},
            "multi_word",
            "2025-08-07_153045_abc12345-dirty_multi_word",
        ),
        ({"commit": None, "dirty": False}, "", "2025-08-07_153045_nogit"),
    ],
)
def test_format_parse_roundtrip(git_info, suffix, expected):
    """Test format -> parse roundtrip for various cases."""
    dirname = format_dirname(TIMESTAMP, git_info, suffix)
    assert dirname == expected

    parsed = parse_dirname(dirname)
    assert parsed["timestamp_str"] == "2025-08-07_153045"
    if git_info["commit"]:
        assert parsed["commit"] == git_info["commit"]
        assert parsed["dirty"] == git_info["dirty"]
    assert parsed["suffix"] == suffix


@pytest.mark.parametrize(
    "invalid_dirname", ["invalid", "2025-08-07", "2025-08-07_153045"]
)
def test_parse_invalid_format(invalid_dirname):
    """Test parsing invalid directory names."""
    with pytest.raises(ValueError, match="Invalid directory format"):
        parse_dirname(invalid_dirname)
