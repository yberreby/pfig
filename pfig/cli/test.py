import json
import time
from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl
import pytest

from ..dirname import parse_timestamp_dir
from ..pfigure import PFigure
from . import compute, get_git_info, render, run

TEST_FIGURES = [
    PFigure(
        "test_figure",
        lambda: (pl.DataFrame({"x": [1, 2], "y": [3, 4]}), {"test": "metadata"}),
        lambda df, meta: (plt.figure(), meta),
    ),
    PFigure(
        "another_figure",
        lambda: (pl.DataFrame({"a": [5, 6]}), {}),
        lambda df, meta: (plt.figure(), meta),
    ),
]


def test_list_command(tmp_path, capsys):
    run(TEST_FIGURES, tmp_path, "default", ["list"])
    captured = capsys.readouterr()
    assert "test_figure" in captured.out
    assert "another_figure" in captured.out


def test_generate_command(tmp_path):
    run(TEST_FIGURES, tmp_path, "default", ["generate", "test_figure"])
    for d in ["render", "compute"]:
        assert (tmp_path / d / "test_figure").exists()


def test_render_command(tmp_path):
    # First generate data
    run(TEST_FIGURES, tmp_path, "default", ["generate", "test_figure"])
    # Then render from cached data
    run(TEST_FIGURES, tmp_path, "default", ["render", "test_figure"])


def test_invalid_figure():
    with pytest.raises(SystemExit):
        run(TEST_FIGURES, Path("/tmp"), "default", ["generate", "nonexistent"])


def test_clean_commands(tmp_path):
    run(TEST_FIGURES, tmp_path, "default", ["generate", "test_figure"])
    run(TEST_FIGURES, tmp_path, "default", ["clean", "-y"])
    run(TEST_FIGURES, tmp_path, "default", ["generate", "test_figure"])
    run(TEST_FIGURES, tmp_path, "default", ["clean", "test_figure", "-y"])


def test_utility_functions():
    git_info = get_git_info()
    assert all(key in git_info for key in ["commit", "dirty"])

    dt, readable = parse_timestamp_dir("2024-01-15_143025_abcd1234")
    assert dt.year == 2024 and "2024-01-15" in readable
