"""CLI infrastructure for pfig."""

import json
import logging
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import matplotlib.pyplot as plt
from matplotlib.figure import Figure as MplFigure
import tyro

from ..pfigure import PFigure
from ..types import Metadata
from ..dirname import (
    format_dirname,
    parse_dirname,
    parse_timestamp_dir,
    validate_dirname_metadata,
    GIT_COMMIT_HASH_LENGTH,
)


# Metadata keys
META_FIGURE = "figure"
META_COMPUTE = "compute"
META_RENDER = "render"
META_OUTPUT = "output"
META_TIMESTAMP = "timestamp"
META_HOSTNAME = "hostname"
META_GIT = "git"
META_DURATION = "duration_seconds"
META_DATA_SOURCE = "data_source"

# File names
METADATA_FILE = "metadata.json"
MANIFEST_FILE = "manifest.json"
FIGURE_EXTENSIONS = ["svg", "png"]

# Constants
BYTES_TO_MB = 1024 * 1024
CONFIRM_PROMPT = "\nProceed? [y/N] "
CONFIRM_RESPONSE = "y"
FIGURES_MODULE = "figures"


def setup_logging() -> None:
    """Setup logging configuration."""
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")


def read_json(path: Path) -> Metadata:
    with open(path) as f:
        return json.load(f)


def write_json(
    path: Path, data: Metadata, indent: int = 2, sort_keys: bool = True
) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, sort_keys=sort_keys)


def load_manifest(root: Path) -> dict[str, str]:
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(f"No {MANIFEST_FILE} found. Pin figures first.")
    return read_json(manifest_path)


def get_latest_run_dir(compute_dir: Path) -> Path:
    """Find the most recent run directory in a compute directory."""
    if not compute_dir.exists():
        raise FileNotFoundError(f"No compute directory found: {compute_dir}")

    data_dirs = [d for d in compute_dir.glob("*") if d.is_dir()]
    if not data_dirs:
        raise FileNotFoundError(f"No compute runs found in {compute_dir}")

    def get_timestamp(path: Path) -> datetime:
        dt, _ = parse_timestamp_dir(path.name)
        return dt

    return max(data_dirs, key=get_timestamp)


def get_git_info() -> Metadata:
    """Get current git commit and dirty status."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        dirty = (
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
            != ""
        )
        return {"commit": commit[:GIT_COMMIT_HASH_LENGTH], "dirty": dirty}
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        logging.warning(f"Failed to get git info: {e}")
        return {"commit": None, "dirty": None}


def gather_run_metadata() -> tuple[datetime, str, Metadata, str]:
    """Gather metadata for a run.

    Returns:
        (timestamp, hostname, git_info, dirname)
    """
    now_utc = datetime.now(timezone.utc)
    hostname = socket.gethostname()
    git_info = get_git_info()
    dirname = format_dirname(now_utc, git_info)
    return now_utc, hostname, git_info, dirname


def compute_data(fig: PFigure, output_dir: Path, logger: logging.Logger) -> Metadata:
    """Compute fresh data and serialize it."""
    logger.info("Computing data...")
    start = time.time()
    result = fig.compute()
    duration = time.time() - start
    logger.info(f"Computed in {duration:.2f}s")

    logger.info("Serializing data...")
    fig.serialize(result.data, output_dir)

    return result.metadata


def load_metadata(data_dir: Path, logger: logging.Logger) -> Metadata:
    """Load metadata from a specific directory."""
    metadata_path = data_dir / METADATA_FILE
    if metadata_path.exists():
        return read_json(metadata_path)
    logger.warning("No metadata found, using empty metadata")
    return {}


def find_latest_compute_dir(
    fig: PFigure, root: Path, logger: logging.Logger
) -> tuple[Path, Metadata]:
    """Find most recent compute directory and load its metadata."""
    logger.info("Finding latest cached data...")
    compute_dir = fig.get_compute_dir(root)
    most_recent_dir = get_latest_run_dir(compute_dir)
    _, readable_time = parse_timestamp_dir(most_recent_dir.name)
    logger.info(f"Using data from {readable_time}")

    # Validate directory name against metadata
    validate_dirname_metadata(most_recent_dir, logger)

    metadata = load_metadata(most_recent_dir, logger)
    return most_recent_dir, metadata


def save_figure(figure: MplFigure, output_dir: Path, logger: logging.Logger) -> None:
    """Save figure in multiple formats."""
    for ext in FIGURE_EXTENSIONS:
        fig_path = output_dir / f"fig.{ext}"
        figure.savefig(fig_path, bbox_inches="tight")
        logger.info(f"Saved figure to {fig_path}")
    plt.close(figure)


def save_metadata(metadata: Metadata, output_dir: Path, logger: logging.Logger) -> None:
    """Save metadata to JSON file."""
    metadata_path = output_dir / METADATA_FILE
    write_json(metadata_path, metadata)
    logger.info(f"Saved metadata to {metadata_path}")


def compute(fig: PFigure, root: Path) -> None:
    """Compute data and save it (no plotting)."""
    logger = logging.getLogger(fig.name)
    logger.info("Starting compute...")
    total_start = time.time()

    # Gather run metadata
    now_utc, hostname, git_info, dirname = gather_run_metadata()

    # Create output directory
    output_dir = fig.get_compute_dir(root, dirname)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compute (user handles saving)
    compute_start = time.time()
    compute_output = compute_data(fig, output_dir, logger)
    compute_duration = time.time() - compute_start

    # Build metadata
    metadata = {
        META_FIGURE: fig.name,
        META_COMPUTE: {
            META_TIMESTAMP: now_utc.isoformat(),
            META_HOSTNAME: hostname,
            META_GIT: git_info,
            META_DURATION: compute_duration,
        },
        META_OUTPUT: compute_output,
    }

    save_metadata(metadata, output_dir, logger)

    total_duration = time.time() - total_start
    logger.info(f"Done! Total time: {total_duration:.2f}s")


def render(
    fig: PFigure, root: Path, style_path: Path, data_dir: Path | None = None
) -> str:
    """Render a figure from data (fresh or cached)."""
    logger = logging.getLogger(fig.name)
    logger.info("Starting render...")
    total_start = time.time()

    # If specific data dir provided, use it; otherwise find latest
    if data_dir:
        metadata = load_metadata(data_dir, logger)
        compute_run = data_dir.name
    else:
        data_dir, metadata = find_latest_compute_dir(fig, root, logger)
        compute_run = data_dir.name

    # Use compute dirname as render dirname for deterministic paths
    dirname = compute_run

    # Gather render metadata (but use compute dirname)
    now_utc = datetime.now(timezone.utc)
    hostname = socket.gethostname()
    git_info = get_git_info()

    # Deserialize and plot
    logger.info("Deserializing data...")
    data = fig.deserialize(data_dir)

    render_start = time.time()
    with plt.style.context(str(style_path)):
        result = fig.plot(data, metadata.get(META_OUTPUT, {}))
    render_duration = time.time() - render_start

    figure = result.figure
    plot_output = result.metadata

    # Build render metadata
    render_metadata = {
        META_FIGURE: fig.name,
        META_COMPUTE: metadata.get(META_COMPUTE, {}),
        "compute_run": compute_run,
        META_RENDER: {
            META_TIMESTAMP: now_utc.isoformat(),
            META_HOSTNAME: hostname,
            META_GIT: git_info,
            META_DURATION: render_duration,
            META_DATA_SOURCE: str(data_dir),
        },
        META_OUTPUT: plot_output,
    }

    # Save figure and metadata to render directory
    output_dir = fig.get_render_dir(root, dirname)
    output_dir.mkdir(parents=True, exist_ok=True)

    save_figure(figure, output_dir, logger)
    save_metadata(render_metadata, output_dir, logger)

    total_duration = time.time() - total_start
    logger.info(f"Done! Total time: {total_duration:.2f}s")

    return dirname


def find_cleanup_targets(
    fig_dict: dict[str, PFigure], root: Path, figure_name: str | None
) -> tuple[list[Path], int]:
    """Find directories to delete and calculate total size."""
    # Determine which figures to clean
    if figure_name:
        figures_to_clean = [(figure_name, fig_dict[figure_name])]
    else:
        figures_to_clean = list(fig_dict.items())

    # Find directories to delete
    dirs_to_delete = []
    total_size = 0

    for _, fig in figures_to_clean:
        # Check both compute and render directories
        for dir_type in ["compute", "render"]:
            if dir_type == "compute":
                base_dir = fig.get_compute_dir(root)
            else:
                base_dir = fig.get_render_dir(root)

            if base_dir.exists():
                # Find all timestamped subdirectories
                for subdir in sorted(base_dir.iterdir()):
                    if subdir.is_dir():
                        # Check if it matches our format
                        try:
                            _ = parse_dirname(subdir.name)
                            dirs_to_delete.append(subdir)
                            # Calculate size
                            for file in subdir.rglob("*"):
                                if file.is_file():
                                    total_size += file.stat().st_size
                        except ValueError:
                            # Skip directories that don't match our format
                            pass

    return dirs_to_delete, total_size


def confirm_deletion(dirs_to_delete: list[Path], total_size: int) -> bool:
    """Show deletion summary and get user confirmation."""
    # Show what will be deleted
    print(f"Will delete {len(dirs_to_delete)} directories:")
    for dir_path in sorted(dirs_to_delete):
        print(f"  {dir_path}")
    print(f"\nTotal size: {total_size / BYTES_TO_MB:.1f} MB")

    response = input(CONFIRM_PROMPT)
    return response.lower() == CONFIRM_RESPONSE


def perform_cleanup(dirs_to_delete: list[Path]) -> None:
    """Delete the specified directories."""
    for dir_path in dirs_to_delete:
        shutil.rmtree(dir_path)
        logging.info(f"Removed {dir_path}")

    print(f"Cleaned {len(dirs_to_delete)} directories.")


def clean_figures(
    fig_dict: dict[str, PFigure],
    root: Path,
    figure_name: str | None,
    skip_confirm: bool,
):
    """Remove generated figure outputs."""
    dirs_to_delete, total_size = find_cleanup_targets(fig_dict, root, figure_name)

    if not dirs_to_delete:
        print("No figure outputs found to clean.")
        return

    # Confirm unless skipped
    if not skip_confirm:
        if not confirm_deletion(dirs_to_delete, total_size):
            print("Cancelled.")
            return

    perform_cleanup(dirs_to_delete)


def pin_figure(
    fig_dict: dict[str, PFigure],
    root: Path,
    figure_name: str,
    specific_run: str | None = None,
):
    """Pin a specific compute run of a figure to the manifest."""
    logger = logging.getLogger(figure_name)
    fig = fig_dict[figure_name]
    compute_dir = fig.get_compute_dir(root)

    if specific_run:
        run_dir = compute_dir / specific_run
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {specific_run} not found for {figure_name}")
    else:
        run_dir = get_latest_run_dir(compute_dir)

    # Update manifest
    manifest_path = root / MANIFEST_FILE
    manifest = read_json(manifest_path) if manifest_path.exists() else {}

    # Check if already pinned to the same version
    was_already_pinned = manifest.get(figure_name) == run_dir.name

    manifest[figure_name] = run_dir.name
    write_json(manifest_path, manifest)
    logger.info(f"Pinned {figure_name} to {run_dir.name}")

    if not was_already_pinned:
        try:
            # Force-add the compute directory (needed because exported/ is in .gitignore)
            _ = subprocess.run(["git", "add", "-f", str(run_dir)], check=True)
            logger.info(f"Force-added {run_dir} to git staging")

            # Also stage the manifest (force-add since exported/ is ignored)
            _ = subprocess.run(["git", "add", "-f", str(manifest_path)], check=True)
            logger.info("Staged manifest.json for commit")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to add to git: {e}")
    else:
        logger.info(f"Already pinned to {run_dir.name}, skipping git staging")


def render_pinned(
    fig_dict: dict[str, PFigure],
    root: Path,
    style_path: Path,
    figure_name: str,
):
    """Render a figure from its pinned compute version."""
    manifest = load_manifest(root)
    if figure_name not in manifest:
        raise ValueError(f"Figure {figure_name} not pinned in manifest")

    fig = fig_dict[figure_name]
    compute_run = manifest[figure_name]
    data_dir = fig.get_compute_dir(root, compute_run)

    if not data_dir.exists():
        raise FileNotFoundError(f"Pinned data directory not found: {data_dir}")

    _ = render(fig, root, style_path, data_dir=data_dir)


def render_from_manifest(
    fig_dict: dict[str, PFigure],
    root: Path,
    style_path: Path,
):
    """Render all figures specified in manifest."""
    manifest = load_manifest(root)

    logger = logging.getLogger("manifest")
    logger.info(f"Rendering {len(manifest)} figures from manifest")

    for fig_name, run_id in manifest.items():
        if fig_name not in fig_dict:
            logger.warning(f"Figure {fig_name} in manifest but not found in codebase")
            continue

        fig = fig_dict[fig_name]
        data_dir = fig.get_compute_dir(root, run_id)

        if not data_dir.exists():
            logger.error(f"Data directory not found for {fig_name}: {data_dir}")
            continue

        logger.info(f"Rendering {fig_name} from run {run_id}")
        _ = render(fig, root, style_path, data_dir=data_dir)


@dataclass
class List:
    """List available figures."""

    pass


@dataclass
class Compute:
    """Compute figure data."""

    figure: Annotated[str, tyro.conf.Positional]


@dataclass
class Render:
    """Render figure from data."""

    figure: Annotated[str, tyro.conf.Positional]
    data_dir: Path | None = None


@dataclass
class Generate:
    """Compute and render figure (full pipeline)."""

    figure: Annotated[str, tyro.conf.Positional]


@dataclass
class Clean:
    """Clean generated outputs."""

    figure: Annotated[str | None, tyro.conf.Positional] = None
    skip_confirm: bool = False


@dataclass
class Pin:
    """Pin figure to manifest."""

    figure: Annotated[str, tyro.conf.Positional]
    run: str | None = None


@dataclass
class RenderPinned:
    """Render figure from pinned version."""

    figure: Annotated[str, tyro.conf.Positional]


@dataclass
class RenderManifest:
    """Render all figures from manifest."""


Command = (
    List | Compute | Render | Generate | Clean | Pin | RenderPinned | RenderManifest
)


def validate_figure(figure: str, fig_dict: dict[str, PFigure]) -> None:
    """Validate figure name."""
    if figure not in fig_dict:
        available = ", ".join(sorted(fig_dict.keys()))
        raise ValueError(f"Unknown figure: {figure}. Available: {available}")


def dispatch_command(
    command: Command, fig_dict: dict[str, PFigure], root: Path, style_path: Path
) -> None:
    """Dispatch command to appropriate handler."""
    if isinstance(command, List):
        print("Available figures:")
        for name in sorted(fig_dict.keys()):
            print(f"  {name}")

    elif isinstance(command, Compute):
        validate_figure(command.figure, fig_dict)
        fig = fig_dict[command.figure]
        compute(fig, root)

    elif isinstance(command, Render):
        validate_figure(command.figure, fig_dict)
        fig = fig_dict[command.figure]
        _ = render(fig, root, style_path, command.data_dir)

    elif isinstance(command, Generate):
        validate_figure(command.figure, fig_dict)
        fig = fig_dict[command.figure]
        compute(fig, root)
        _ = render(fig, root, style_path)

    elif isinstance(command, Clean):
        if command.figure:
            validate_figure(command.figure, fig_dict)
        clean_figures(fig_dict, root, command.figure, command.skip_confirm)

    elif isinstance(command, Pin):
        validate_figure(command.figure, fig_dict)
        pin_figure(fig_dict, root, command.figure, command.run)

    elif isinstance(command, RenderPinned):
        validate_figure(command.figure, fig_dict)
        render_pinned(fig_dict, root, style_path, command.figure)

    else:  # RenderManifest
        render_from_manifest(fig_dict, root, style_path)


def run(figures: list[PFigure], root: str | Path, style: str | Path, argv: list[str]):
    """Run the CLI with given figures and configuration."""
    setup_logging()
    logging.info(f"Working directory: {Path.cwd()}")

    root = Path(root)
    style_path = Path(style)
    fig_dict = {fig.name: fig for fig in figures}

    command = tyro.cli(Command, args=argv)
    dispatch_command(command, fig_dict, root, style_path)


def discover_figures() -> list[PFigure]:
    """Auto-discover figures from the current working directory.

    Imports the FIGURES_MODULE from the current directory and extracts
    the FIGURES list. The module can be either figures.py or figures/.

    Returns:
        List of discovered PFigure instances

    Raises:
        ImportError: If module cannot be imported
        AttributeError: If FIGURES list is not found
    """
    import sys
    import importlib

    cwd = Path.cwd()
    logger = logging.getLogger("discovery")

    # Add cwd to path if not already there
    if str(cwd) not in sys.path:
        logger.info(f"Adding {cwd} to sys.path")
        sys.path.insert(0, str(cwd))

    try:
        module = importlib.import_module(FIGURES_MODULE)
        logger.info(f"Imported {FIGURES_MODULE} from {module.__file__}")
    except ImportError as e:
        raise ImportError(
            f"Could not import '{FIGURES_MODULE}' module from {cwd}. "
            f"Ensure you have either {FIGURES_MODULE}.py or {FIGURES_MODULE}/ with __init__.py"
        ) from e

    if not hasattr(module, "FIGURES"):
        raise AttributeError(f"Module '{FIGURES_MODULE}' must define a FIGURES list")

    figures = module.FIGURES
    logger.info(f"Discovered {len(figures)} figure(s): {[f.name for f in figures]}")
    return figures


def main():
    """Main CLI entry point with auto-discovery."""
    import sys

    setup_logging()

    try:
        figures = discover_figures()
    except (FileNotFoundError, ImportError, AttributeError) as e:
        logging.error(f"Error discovering figures: {e}")
        sys.exit(1)

    # Use sensible defaults
    root = Path("exported")
    style = Path("default")

    run(figures, root, style, argv=sys.argv[1:])
