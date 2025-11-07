"""Directory naming utilities for pfig."""

import json
from datetime import datetime, timezone
from pathlib import Path

# Constants
TIMESTAMP_FORMAT = "%Y-%m-%d_%H%M%S"
NOGIT_MARKER = "nogit"
DIRTY_SUFFIX = "-dirty"
DIRTY_SUFFIX_LENGTH = 6
GIT_COMMIT_HASH_LENGTH = 8
SECONDS_IN_MINUTE = 60
SECONDS_IN_HOUR = 3600
SECONDS_IN_DAY = 86400


def format_dirname(timestamp: datetime, git_info: dict, suffix: str = "") -> str:
    """Format directory name from components.

    Format: YYYY-MM-DD_HHMMSS_commit[-dirty]_[suffix]
    """
    timestamp_str = timestamp.strftime(TIMESTAMP_FORMAT)
    git_commit = git_info["commit"] or NOGIT_MARKER
    dirty_marker = DIRTY_SUFFIX if git_info["dirty"] else ""

    parts = [timestamp_str, f"{git_commit}{dirty_marker}"]
    if suffix:
        parts.append(suffix)

    return "_".join(parts)


def parse_dirname(dirname: str) -> dict:
    """Parse directory name into components."""
    parts = dirname.split("_")
    if len(parts) < 3:  # YYYY-MM-DD_HHMMSS_commit minimum
        raise ValueError(f"Invalid directory format: {dirname}")

    # Parse timestamp
    date_str = parts[0]
    time_str = parts[1]
    timestamp_str = f"{date_str}_{time_str}"

    # Parse git info
    git_part = parts[2]
    if git_part.endswith(DIRTY_SUFFIX):
        commit = git_part[:-DIRTY_SUFFIX_LENGTH]
        dirty = True
    else:
        commit = git_part
        dirty = False

    # Suffix is everything after the third part
    suffix = "_".join(parts[3:]) if len(parts) > 3 else ""

    return {
        "timestamp_str": timestamp_str,
        "commit": commit,
        "dirty": dirty,
        "suffix": suffix,
    }


def parse_timestamp_string(timestamp_str: str) -> datetime:
    """Parse timestamp string to datetime with UTC timezone."""
    return datetime.strptime(timestamp_str, TIMESTAMP_FORMAT).replace(
        tzinfo=timezone.utc
    )


def format_time_ago(dt: datetime) -> str:
    """Format a datetime as 'X ago' relative to now."""
    now_utc = datetime.now(timezone.utc)
    delta = now_utc - dt

    if delta.total_seconds() < SECONDS_IN_MINUTE:
        return f"{int(delta.total_seconds())}s ago"
    elif delta.total_seconds() < SECONDS_IN_HOUR:
        return f"{int(delta.total_seconds() / SECONDS_IN_MINUTE)}m ago"
    elif delta.total_seconds() < SECONDS_IN_DAY:
        return f"{int(delta.total_seconds() / SECONDS_IN_HOUR)}h ago"
    else:
        return f"{int(delta.days)}d ago"


def parse_timestamp_dir(dirname: str) -> tuple[datetime, str]:
    """Parse timestamp from directory name and return datetime and human-readable string."""
    parsed = parse_dirname(dirname)

    # Parse timestamp
    dt = parse_timestamp_string(parsed["timestamp_str"])

    # Format datetime in local timezone with relative time
    local_dt = dt.astimezone()
    readable = f"{local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} ({format_time_ago(dt)})"

    return dt, readable


def validate_dirname_metadata(dirpath: Path, logger) -> None:
    """Validate that directory name matches metadata.json contents."""
    metadata_path = dirpath / "metadata.json"
    if not metadata_path.exists():
        logger.warning(f"No metadata.json found in {dirpath}")
        return

    # Load metadata
    with open(metadata_path) as f:
        metadata = json.load(f)

    # Parse directory name
    parsed = parse_dirname(dirpath.name)

    # Check timestamp
    if "generated_at_utc" in metadata:
        # Parse metadata timestamp
        meta_dt = datetime.fromisoformat(metadata["generated_at_utc"].rstrip("Z"))
        if not meta_dt.tzinfo:
            meta_dt = meta_dt.replace(tzinfo=timezone.utc)

        # Parse dirname timestamp
        dir_dt = parse_timestamp_string(parsed["timestamp_str"])

        # Compare timestamps (allow 1 second tolerance)
        if abs((meta_dt - dir_dt).total_seconds()) > 1:
            raise ValueError(
                f"Timestamp mismatch in {dirpath.name}: "
                f"dirname={dir_dt.isoformat()}, metadata={meta_dt.isoformat()}"
            )

    # Check git info
    if "git" in metadata:
        git_info = metadata["git"]
        if (
            "commit" in git_info
            and git_info["commit"]
            and parsed["commit"] != NOGIT_MARKER
        ):
            # Compare commit (first 8 chars)
            meta_commit = (
                git_info["commit"][:GIT_COMMIT_HASH_LENGTH]
                if git_info["commit"]
                else None
            )
            if meta_commit and meta_commit != parsed["commit"]:
                raise ValueError(
                    f"Git commit mismatch in {dirpath.name}: "
                    f"dirname={parsed['commit']}, metadata={meta_commit}"
                )

        # Check dirty state
        if "dirty" in git_info and git_info["dirty"] != parsed["dirty"]:
            raise ValueError(
                f"Git dirty state mismatch in {dirpath.name}: "
                f"dirname={parsed['dirty']}, metadata={git_info['dirty']}"
            )
