#!/usr/bin/env python3
"""Install into a new directory only; never overwrite project data."""
import os
from pathlib import Path
import shutil
import sys


def install(destination):
    if not destination or not destination.strip():
        raise ValueError("Choose a new installation directory")
    source = Path(__file__).resolve().parent.parent / "checklist-reviewer"
    dest = Path(os.path.abspath(destination))
    # Refuse symlink parents as well as existing/dangling destinations.
    for part in [dest, *dest.parents]:
        if part.is_symlink():
            raise ValueError("Installation path must not contain symbolic links")
    if dest.exists() or not dest.parent.is_dir():
        raise ValueError("Destination must be new and its parent must already exist")
    if source == dest or source in dest.parents:
        raise ValueError("Cannot install inside the template")
    # mkdir is the exclusive claim; copytree also refuses an existing destination.
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(
        "node_modules", "dist", "projects", "reviews", "review-results", "*.log"
    ))
    print("Installed checklist reviewer into the requested new directory.")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Usage: install_checklist_reviewer.py <new-directory>")
        install(sys.argv[1])
    except (OSError, ValueError):
        print("Installation failed: use a new directory in an existing, non-symlink parent. Existing files were not overwritten.", file=sys.stderr)
        sys.exit(1)
