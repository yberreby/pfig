from pathlib import Path

import polars as pl
import matplotlib.pyplot as plt

from pfig import PFigure, ComputeResult, PlotResult, Metadata


def compute() -> ComputeResult:
    sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
    dt = 0.01
    n_steps = 10000

    x, y, z = 1.0, 1.0, 1.0
    points = []

    for _ in range(n_steps):
        dx = sigma * (y - x)
        dy = x * (rho - z) - y
        dz = x * y - beta * z

        x += dx * dt
        y += dy * dt
        z += dz * dt

        points.append({"x": x, "y": y, "z": z})

    df = pl.DataFrame(points)
    return ComputeResult(
        data=df,
        metadata={
            "sigma": sigma,
            "rho": rho,
            "beta": beta,
            "dt": dt,
            "n_steps": n_steps,
        },
    )


def serialize(data: pl.DataFrame, output_dir: Path) -> None:
    data.write_parquet(output_dir / "data.parquet")


def deserialize(data_dir: Path) -> pl.DataFrame:
    return pl.read_parquet(data_dir / "data.parquet")


def plot(data: pl.DataFrame, _meta: Metadata) -> PlotResult:
    fig = plt.figure(figsize=(12, 5))

    ax1 = fig.add_subplot(121, projection="3d")
    ax1.plot(data["x"], data["y"], data["z"], linewidth=0.5, alpha=0.7)
    ax1.set_xlabel("X")
    ax1.set_ylabel("Y")
    ax1.set_zlabel("Z")
    ax1.set_title("Lorenz Attractor")

    ax2 = fig.add_subplot(122)
    ax2.plot(data["x"], data["z"], linewidth=0.5, alpha=0.7)
    ax2.set_xlabel("X")
    ax2.set_ylabel("Z")
    ax2.set_title("X-Z Projection")
    ax2.grid(alpha=0.3)

    fig.tight_layout()

    return PlotResult(figure=fig, metadata={"views": ["3d", "xz_projection"]})


figure = PFigure("lorenz", compute, serialize, deserialize, plot)
