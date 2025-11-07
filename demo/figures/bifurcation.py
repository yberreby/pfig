from pathlib import Path

import numpy as np
import polars as pl
import matplotlib.pyplot as plt

from pfig import PFigure, ComputeResult, PlotResult, Metadata


def compute() -> ComputeResult:
    r_values = np.linspace(2.5, 4.0, 500)
    iterations = 1000
    last_n = 100

    results = []
    for r in r_values:
        x = 0.5
        for _ in range(iterations - last_n):
            x = r * x * (1 - x)

        for _ in range(last_n):
            x = r * x * (1 - x)
            results.append({"r": r, "x": x})

    df = pl.DataFrame(results)
    return ComputeResult(
        data=df,
        metadata={
            "r_range": [float(r_values.min()), float(r_values.max())],
            "n_points": len(r_values),
            "iterations": iterations,
            "n_rows": len(df),
        },
    )


def serialize(data: pl.DataFrame, output_dir: Path) -> None:
    data.write_parquet(output_dir / "data.parquet")


def deserialize(data_dir: Path) -> pl.DataFrame:
    return pl.read_parquet(data_dir / "data.parquet")


def plot(data: pl.DataFrame, _meta: Metadata) -> PlotResult:
    fig, ax = plt.subplots(figsize=(10, 6))

    sample = data.sample(fraction=0.1, seed=42) if len(data) > 50000 else data
    ax.scatter(sample["r"], sample["x"], s=0.1, alpha=0.5, c="black")

    ax.set_xlabel("Growth rate (r)")
    ax.set_ylabel("Population")
    ax.set_title("Logistic Map Bifurcation Diagram")
    ax.grid(alpha=0.3)

    return PlotResult(figure=fig, metadata={"n_plotted": len(sample)})


figure = PFigure("bifurcation", compute, serialize, deserialize, plot)
