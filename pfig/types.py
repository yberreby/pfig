"""Core types for pfig."""

from typing import Any, NamedTuple
from matplotlib.figure import Figure as MatplotlibFigure

Metadata = dict[str, Any]


class ComputeResult(NamedTuple):
    """Result from compute(): data and metadata."""

    data: Any
    metadata: Metadata


class PlotResult(NamedTuple):
    """Result from plot(): figure and metadata."""

    figure: MatplotlibFigure
    metadata: Metadata
