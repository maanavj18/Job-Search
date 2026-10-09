from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    override = os.environ.get("JOBSEARCH_DATA_DIR")
    if override:
        path = Path(override)
    else:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
        if base:
            path = Path(base) / "JobSearch"
        else:
            path = Path.home() / ".local" / "share" / "JobSearch"
    path.mkdir(parents=True, exist_ok=True)
    return path
