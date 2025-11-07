"""CLI infrastructure for pfig."""

# TODO: general refactoring / code review for this module
# Does the job for now, but not fully validated.
# TODO: dedup "No compute directory found for ..." messages / code paths.

import argparse
import time
import json
import logging
import subprocess
import socket
import pickle
from pathlib import Path
from datetime import datetime, timezone
import matplotlib.pyplot as plt
from matplotlib.figure import Figure as MplFigure
import polars as pl
from typing import Any

from ..pfigure import PFigure
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
DATA_FILE = "data.parquet"
METADATA_FILE = "metadata.json"
FIGURE_EXTENSIONS = ["svg", "png"]

# Constants
BYTES_TO_MB = 1024 * 1024
CONFIRM_PROMPT = "\nProceed? [y/N] "
CONFIRM_RESPONSE = "y"


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")


def get_data_filename(data: Any) -> str:
    """Get appropriate filename based on data type."""
    if isinstance(data, pl.DataFrame):
        return "data.parquet"
    else:
        return "data.pkl"


def save_data(data: Any, output_dir: Path, logger) -> None:
    """Save data in appropriate format."""
    filename = get_data_filename(data)
    data_path = output_dir / filename

    if isinstance(data, pl.DataFrame):
        data.write_parquet(data_path)
        logger.info(f"Saved {len(data)} rows to {data_path}")
    else:
        with open(data_path, "wb") as f:
            pickle.dump(data, f)
        logger.info(f"Saved data to {data_path}")


def load_data(data_dir: Path) -> Any:
    """Load data by checking which file exists."""
    # Check for parquet first (backward compat)
    parquet_path = data_dir / "data.parquet"
    if parquet_path.exists():
        return pl.read_parquet(parquet_path)

    # Check for pickle
    pkl_path = data_dir / "data.pkl"
    if pkl_path.exists():
        with open(pkl_path, "rb") as f:
            return pickle.load(f)

    raise FileNotFoundError(f"No data file found in {data_dir}")


def get_git_info() -> dict:
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


def gather_run_metadata() -> tuple[datetime, str, dict, str]:
    """Gather metadata for a run.

    Returns:
        (timestamp, hostname, git_info, dirname)
    """
    now_utc = datetime.now(timezone.utc)
    hostname = socket.gethostname()
    git_info = get_git_info()
    dirname = format_dirname(now_utc, git_info)
    return now_utc, hostname, git_info, dirname


def compute_data(fig: PFigure, logger) -> tuple[Any, dict]:
    """Compute fresh data."""
    logger.info("Computing data...")
    start = time.time()
    data, metadata = fig.compute()
    duration = time.time() - start

    # Generic size reporting
    size_info = f"{len(data)} rows" if isinstance(data, pl.DataFrame) else "data"
    logger.info(f"Computed {size_info} ({duration:.2f}s)")
    return data, metadata


def load_specific_data(fig: PFigure, data_dir: Path, logger) -> tuple[Any, dict]:
    """Load data from a specific directory."""
    data = load_data(data_dir)

    # Generic size reporting
    size_info = f"{len(data)} rows" if isinstance(data, pl.DataFrame) else "data"
    logger.info(f"Loaded {size_info} from {data_dir}")

    metadata_path = data_dir / METADATA_FILE
    if metadata_path.exists():
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    else:
        logger.warning("No metadata found, using empty metadata")
        metadata = {}

    return data, metadata


def load_latest_data(fig: PFigure, root: Path, logger) -> tuple[Any, dict, Path]:
    """Load most recent cached data and metadata.

    Returns:
        (data, metadata, data_dir) tuple
    """
    logger.info("Loading latest cached data...")

    # Find all data files in compute subdirectories
    compute_dir = fig.get_compute_dir(root)
    if not compute_dir.exists():
        raise FileNotFoundError(f"No compute directory found for {fig.name}")

    data_dirs = [d for d in compute_dir.glob("*") if d.is_dir()]

    if not data_dirs:
        raise FileNotFoundError(f"No cached data found in {compute_dir}")

    # Filter to only directories that have data files
    valid_data_dirs = []
    for d in data_dirs:
        if (d / "data.parquet").exists() or (d / "data.pkl").exists():
            valid_data_dirs.append(d)

    if not valid_data_dirs:
        raise FileNotFoundError(f"No cached data found in {compute_dir}")

    # Sort by timestamp from directory name
    def get_timestamp(path: Path) -> datetime:
        dt, _ = parse_timestamp_dir(path.name)
        return dt

    most_recent_dir = max(valid_data_dirs, key=get_timestamp)
    _, readable_time = parse_timestamp_dir(most_recent_dir.name)
    logger.info(f"Loading from {readable_time}")

    # Validate directory name against metadata
    validate_dirname_metadata(most_recent_dir, logger)

    data, metadata = load_specific_data(fig, most_recent_dir, logger)
    return data, metadata, most_recent_dir


def save_figure(figure: MplFigure, output_dir: Path, logger):
    """Save figure in multiple formats."""
    for ext in FIGURE_EXTENSIONS:
        fig_path = output_dir / f"fig.{ext}"
        figure.savefig(fig_path, bbox_inches="tight")
        logger.info(f"Saved figure to {fig_path}")
    plt.close(figure)


def save_metadata(metadata: dict, output_dir: Path, logger):
    """Save metadata to JSON file."""
    metadata_path = output_dir / METADATA_FILE
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Saved metadata to {metadata_path}")


def compute(fig: PFigure, root: Path):
    """Compute data and save it (no plotting)."""
    logger = logging.getLogger(fig.name)
    logger.info("Starting compute...")
    total_start = time.time()

    # Gather run metadata
    now_utc, hostname, git_info, dirname = gather_run_metadata()

    # Compute
    compute_start = time.time()
    df, compute_output = compute_data(fig, logger)
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

    # Save data and metadata to compute directory
    output_dir = fig.get_compute_dir(root, dirname)
    output_dir.mkdir(parents=True, exist_ok=True)

    save_data(df, output_dir, logger)

    save_metadata(metadata, output_dir, logger)

    total_duration = time.time() - total_start
    logger.info(f"Done! Computed {len(df)} rows in {total_duration:.2f}s")


def render(fig: PFigure, root: Path, style_path: Path, data_dir: Path | None = None):
    """Render a figure from data (fresh or cached)."""
    logger = logging.getLogger(fig.name)
    logger.info("Starting render...")
    total_start = time.time()

    # If specific data dir provided, use it; otherwise find latest
    if data_dir:
        df, metadata = load_specific_data(fig, data_dir, logger)
        compute_run = data_dir.name  # Extract run ID from path
    else:
        df, metadata, data_dir = load_latest_data(fig, root, logger)
        compute_run = data_dir.name

    # Use compute dirname as render dirname for deterministic paths
    dirname = compute_run

    # Gather render metadata (but use compute dirname)
    now_utc = datetime.now(timezone.utc)
    hostname = socket.gethostname()
    git_info = get_git_info()

    # Create plot
    render_start = time.time()
    with plt.style.context(str(style_path)):
        figure, plot_output = fig.plot(df, metadata[META_OUTPUT])
    render_duration = time.time() - render_start

    # Build render metadata
    render_metadata = {
        META_FIGURE: fig.name,
        META_COMPUTE: metadata[META_COMPUTE],
        "compute_run": compute_run,  # Track which compute run was used
        META_RENDER: {
            META_TIMESTAMP: now_utc.isoformat(),
            META_HOSTNAME: hostname,
            META_GIT: git_info,
            META_DURATION: render_duration,
            META_DATA_SOURCE: str(data_dir) if data_dir else "latest",
        },
        META_OUTPUT: plot_output,
    }

    # Save figure and metadata to render directory
    output_dir = fig.get_render_dir(root, dirname)
    output_dir.mkdir(parents=True, exist_ok=True)

    save_figure(figure, output_dir, logger)
    save_metadata(render_metadata, output_dir, logger)

    total_duration = time.time() - total_start
    logger.info(f"Done! Rendered in {total_duration:.2f}s")

    return dirname  # Return the actual run ID created


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

    for name, fig in figures_to_clean:
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
                            parse_dirname(subdir.name)
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
    import shutil

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
        # Use specified run
        run_dir = compute_dir / specific_run
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {specific_run} not found for {figure_name}")
    else:
        # Find latest compute run
        if not compute_dir.exists():
            raise FileNotFoundError(f"No compute directory found for {figure_name}")

        data_dirs = [d for d in compute_dir.glob("*") if d.is_dir()]
        if not data_dirs:
            raise FileNotFoundError(f"No compute runs found for {figure_name}")

        # Sort by timestamp from directory name
        def get_timestamp(path: Path) -> datetime:
            dt, _ = parse_timestamp_dir(path.name)
            return dt

        run_dir = max(data_dirs, key=get_timestamp)

    # Update manifest
    manifest_path = root / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

    # Check if already pinned to the same version
    was_already_pinned = manifest.get(figure_name) == run_dir.name

    manifest[figure_name] = run_dir.name

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    logger.info(f"Pinned {figure_name} to {run_dir.name}")

    if not was_already_pinned:
        try:
            # Force-add the compute directory (needed because exported/ is in .gitignore)
            subprocess.run(["git", "add", "-f", str(run_dir)], check=True)
            logger.info(f"Force-added {run_dir} to git staging")

            # Also stage the manifest (force-add since exported/ is ignored)
            subprocess.run(["git", "add", "-f", str(manifest_path)], check=True)
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
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("No manifest.json found. Pin a figure first.")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    if figure_name not in manifest:
        raise ValueError(f"Figure {figure_name} not pinned in manifest")

    fig = fig_dict[figure_name]
    compute_run = manifest[figure_name]
    data_dir = fig.get_compute_dir(root, compute_run)

    if not data_dir.exists():
        raise FileNotFoundError(f"Pinned data directory not found: {data_dir}")

    render(fig, root, style_path, data_dir=data_dir)


def render_from_manifest(
    fig_dict: dict[str, PFigure],
    root: Path,
    style_path: Path,
    force: bool = False,
):
    """Render all figures specified in manifest."""
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("No manifest.json found. Pin figures first.")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

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
        render(fig, root, style_path, data_dir=data_dir)


def setup_cli() -> None:
    """Setup CLI environment and logging."""
    setup_logging()
    logging.info(f"Working directory: {Path.cwd()}")


def create_argument_parser(fig_dict: dict[str, PFigure]) -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Paper figure generation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available figures: {', '.join(sorted(fig_dict.keys()))}",
    )

    # Add subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    subparsers.add_parser("list", help="List available figures")

    # Compute command
    compute_parser = subparsers.add_parser("compute", help="Compute figure data")
    compute_parser.add_argument(
        "figure", choices=fig_dict.keys(), help="Figure to compute"
    )

    # Render command
    render_parser = subparsers.add_parser("render", help="Render figure from data")
    render_parser.add_argument(
        "figure", choices=fig_dict.keys(), help="Figure to render"
    )
    render_parser.add_argument(
        "--data-dir", type=Path, help="Specific data directory to use"
    )

    # Generate command (compute + render)
    generate_parser = subparsers.add_parser(
        "generate", help="Compute and render figure (full pipeline)"
    )
    generate_parser.add_argument(
        "figure", choices=fig_dict.keys(), help="Figure to generate"
    )

    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Clean generated outputs")
    clean_parser.add_argument(
        "figure", nargs="?", help="Specific figure to clean (or all)"
    )
    clean_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation"
    )

    # Pin command
    pin_parser = subparsers.add_parser("pin", help="Pin figure to manifest")
    pin_parser.add_argument("figure", choices=fig_dict.keys(), help="Figure to pin")
    pin_parser.add_argument("--run", help="Specific run ID to pin (default: latest)")

    # Render-pinned command
    render_pinned_parser = subparsers.add_parser(
        "render-pinned", help="Render figure from pinned version"
    )
    render_pinned_parser.add_argument(
        "figure", choices=fig_dict.keys(), help="Figure to render"
    )

    # Render-manifest command
    manifest_parser = subparsers.add_parser(
        "render-manifest", help="Render all figures from manifest"
    )
    manifest_parser.add_argument(
        "--force", action="store_true", help="Force re-render even if outputs exist"
    )

    return parser


def route_command(
    args: argparse.Namespace, fig_dict: dict[str, PFigure], root: Path, style_path: Path
) -> None:
    """Route parsed arguments to appropriate command handlers."""
    if not args.command:
        return  # Will show help in main function

    if args.command == "list":
        print("Available figures:")
        for name in sorted(fig_dict.keys()):
            print(f"  {name}")
        return

    if args.command == "compute":
        fig = fig_dict[args.figure]
        compute(fig, root)
        return

    if args.command == "render":
        fig = fig_dict[args.figure]
        render(fig, root, style_path, args.data_dir)
        return

    if args.command == "generate":
        fig = fig_dict[args.figure]
        compute(fig, root)
        render(fig, root, style_path)
        return

    if args.command == "clean":
        clean_figures(fig_dict, root, args.figure, args.yes)
        return

    if args.command == "pin":
        pin_figure(fig_dict, root, args.figure, args.run)
        return

    if args.command == "render-pinned":
        render_pinned(fig_dict, root, style_path, args.figure)
        return

    if args.command == "render-manifest":
        render_from_manifest(fig_dict, root, style_path, args.force)
        return


def run(figures: list[PFigure], root: str | Path, style: str | Path, argv: list[str]):
    """Run the CLI with given figures and configuration."""
    setup_cli()

    root = Path(root)
    style_path = Path(style)
    fig_dict = {fig.name: fig for fig in figures}

    parser = create_argument_parser(fig_dict)
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    route_command(args, fig_dict, root, style_path)
