from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

from ..types import ComputeResult, PlotResult, Metadata


@dataclass
class PFigure:
    """Simple dataclass-based paper figure with composable compute/serialize/deserialize/plot functions.

    compute: Pure computation, returns ComputeResult
    serialize: Saves data to output_dir
    deserialize: Loads data from data_dir
    plot: Pure visualization, returns PlotResult
    """

    name: str
    compute: Callable[[], ComputeResult]
    serialize: Callable[[Any, Path], None]
    deserialize: Callable[[Path], Any]
    plot: Callable[[Any, Metadata], PlotResult]

    def get_compute_dir(self, root: Path, run_id: str | None = None) -> Path:
        """Get the compute directory for this figure.

        Args:
            root: Root export directory
            run_id: Optional specific run ID (timestamp_githash)

        Returns:
            Path to compute directory (with or without run_id)
        """
        base = root / "compute" / self.name
        return base / run_id if run_id else base

    def get_render_dir(self, root: Path, run_id: str | None = None) -> Path:
        """Get the render directory for this figure.

        Args:
            root: Root export directory
            run_id: Optional specific run ID (timestamp_githash)

        Returns:
            Path to render directory (with or without run_id)
        """
        base = root / "render" / self.name
        return base / run_id if run_id else base
