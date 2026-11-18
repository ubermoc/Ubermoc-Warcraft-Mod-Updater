# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Find and clear an addon's saved settings: the files the game keeps in WTF for it."""

from __future__ import annotations

import os
from pathlib import Path


def wtf_dir(game_path: str | Path) -> Path | None:
    """The game's WTF folder, whatever its case (Proton ignores case)."""
    root = Path(game_path)
    try:
        return next((e for e in root.iterdir() if e.name.lower() == "wtf" and e.is_dir()), None)
    except OSError:
        return None


def saved_files(game_path: str | Path, names: list[str]) -> list[Path]:
    """Every saved-variables file (and its .bak) for these SavedVariables names, in every account and character."""
    wanted = {n.lower() for n in names if n}
    wtf = wtf_dir(game_path)
    if not wanted or wtf is None:
        return []
    account = next((e for e in wtf.iterdir() if e.name.lower() == "account" and e.is_dir()), None) if wtf.is_dir() else None
    if account is None:
        return []
    found: list[Path] = []
    for root, _dirs, files in os.walk(account, followlinks=False):
        if os.path.basename(root).lower() != "savedvariables":
            continue
        for name in files:
            low = name.lower()
            base = low[:-4] if low.endswith(".bak") else low
            path = Path(root, name)
            if base.endswith(".lua") and base[:-4] in wanted and path.is_file() and not path.is_symlink():
                found.append(path)
    return sorted(found)


def clear(game_path: str | Path, names: list[str]) -> int:
    """Delete the saved files. Returns how many were removed."""
    files = saved_files(game_path, names)
    removed = 0
    for path in files:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError as e:
            raise OSError(f"Couldn't delete {path.name}: {e}") from e
    return removed
