"""Filesystem boundaries for runtime-only candidate data."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def external_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path == PROJECT_ROOT or PROJECT_ROOT in path.parents:
        raise ValueError("Choose a path outside the project folder; personal data must not be stored here")
    return path


def output_directory(value: str | Path) -> Path:
    path = external_path(value)
    if path.exists() and not path.is_dir():
        raise ValueError("Results destination must be a folder")
    return path
