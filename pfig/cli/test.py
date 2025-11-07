import json
import time
from pathlib import Path
import pytest
import polars as pl
import matplotlib.pyplot as plt
from ..pfigure import PFigure
from . import run, get_git_info, compute, render
from ..dirname import parse_timestamp_dir

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
    assert (tmp_path / "test_figure").exists()


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


def test_metadata_preservation(tmp_path):
    test_fig = PFigure(
        "test_metadata",
        lambda: (
            pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}),
            {"algorithm": "test_algo"},
        ),
        lambda df, meta: (
            plt.figure(),
            {
                "plot_type": "line",
                "used_algorithm": meta["algorithm"]
                if "algorithm" in meta
                else "unknown",
            },
        ),
    )

    style_path = tmp_path / "test.mplstyle"
    style_path.write_text("figure.dpi: 100\n")

    compute(test_fig, tmp_path)
    first_meta = json.load(
        open(list((tmp_path / "test_metadata").glob("*"))[0] / "metadata.json")
    )

    time.sleep(1.1)  # Ensure different timestamps for directory names
    render(test_fig, tmp_path, style_path)

    all_runs = sorted((tmp_path / "test_metadata").glob("*"))
    assert len(all_runs) == 2
    second_meta = json.load(open(all_runs[1] / "metadata.json"))

    # Compute metadata preserved, plot metadata fresh
    assert second_meta["compute"] == first_meta["compute"]
    assert second_meta["render"]["data_source"] in ["latest", "cache"]
    assert second_meta["output"]["used_algorithm"] == "test_algo"
