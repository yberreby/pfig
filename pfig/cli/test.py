from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl
import pytest

from ..dirname import parse_timestamp_dir
from ..pfigure import PFigure
from ..types import ComputeResult, PlotResult, Metadata
from . import get_git_info, run


def make_test_figure(
    name: str, data_dict: dict[str, list[int]], metadata: Metadata | None = None
) -> PFigure:
    def compute() -> ComputeResult:
        return ComputeResult(data=pl.DataFrame(data_dict), metadata=metadata or {})

    def serialize(data: pl.DataFrame, output_dir: Path) -> None:
        data.write_parquet(output_dir / "data.parquet")

    def deserialize(data_dir: Path) -> pl.DataFrame:
        return pl.read_parquet(data_dir / "data.parquet")

    def plot(_data: pl.DataFrame, meta: Metadata) -> PlotResult:
        return PlotResult(figure=plt.figure(), metadata=meta)

    return PFigure(name, compute, serialize, deserialize, plot)


TEST_FIGURES = [
    make_test_figure("test_figure", {"x": [1, 2], "y": [3, 4]}, {"test": "metadata"}),
    make_test_figure("another_figure", {"a": [5, 6]}),
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
    with pytest.raises(ValueError):
        run(TEST_FIGURES, Path("/tmp"), "default", ["generate", "nonexistent"])


def test_clean_commands(tmp_path):
    run(TEST_FIGURES, tmp_path, "default", ["generate", "test_figure"])
    run(TEST_FIGURES, tmp_path, "default", ["clean", "--skip-confirm"])
    run(TEST_FIGURES, tmp_path, "default", ["generate", "test_figure"])
    run(TEST_FIGURES, tmp_path, "default", ["clean", "test_figure", "--skip-confirm"])


def test_utility_functions():
    git_info = get_git_info()
    assert all(key in git_info for key in ["commit", "dirty"])

    dt, readable = parse_timestamp_dir("2024-01-15_143025_abcd1234")
    assert dt.year == 2024 and "2024-01-15" in readable
