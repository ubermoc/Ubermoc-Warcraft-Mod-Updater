# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Check an addon zip and swap it into the AddOns folder, or put everything back."""

from __future__ import annotations

import os
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .toc import toc_name_matches

MAX_UNPACKED_BYTES = 1024 * 1024 * 1024
# Game clients only. Helpers such as WowVoiceProxy.exe run beside them and name no game.
_WOW_EXE = re.compile(r"(^|[\\/])wow(classic)?[tb]?(-64)?\.exe$", re.IGNORECASE)
_GAME_DIR = re.compile(r"[\\/](_[a-z0-9_]+_)[\\/]", re.IGNORECASE)


class InstallError(Exception):
    """A problem to show to the user as it is."""


def _is_safe_name(name: str) -> bool:
    if "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    return ".." not in PurePosixPath(name).parts


def check_zip(zip_path: str | Path) -> list[str]:
    """The addon folders in a zip. Raises InstallError if it isn't safe to unpack."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            if z.testzip() is not None:
                raise InstallError("The downloaded zip is damaged.")
    except (zipfile.BadZipFile, OSError) as e:
        raise InstallError(f"The download isn't a usable zip: {e}") from e

    total = 0
    tocs: dict[str, bool] = {}
    for info in infos:
        name = info.filename
        if not _is_safe_name(name):
            raise InstallError(f"The zip contains an unsafe path: {name}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise InstallError(f"The zip contains a link: {name}")
        total += info.file_size
        if total > MAX_UNPACKED_BYTES:
            raise InstallError("The zip is too large to unpack.")
        parts = PurePosixPath(name).parts
        if len(parts) < 2 and not info.is_dir():
            continue  # a loose file beside the addon folders, such as a readme
        top = parts[0]
        tocs.setdefault(top, False)
        if len(parts) == 2 and not info.is_dir() and toc_name_matches(top, parts[1]):
            tocs[top] = True

    if not tocs:
        raise InstallError("The zip has no addon folders in it.")
    missing = [folder for folder, has_toc in tocs.items() if not has_toc]
    if missing:
        raise InstallError(f"This isn't a packaged addon. {missing[0]} has no matching .toc file.")
    return sorted(tocs)


def _existing(addons_dir: Path, folder: str) -> Path | None:
    """The installed folder of this name, whatever its case. Proton ignores case."""
    wanted = folder.lower()
    for entry in addons_dir.iterdir():
        if entry.name.lower() == wanted:
            return entry
    return None


def install_zip(zip_path: str | Path, addons_dir: str | Path, stale: list[str] | None = None) -> list[str]:
    """Replace the zip's folders in AddOns and remove stale ones, all or nothing."""
    folders = check_zip(zip_path)
    addons = Path(addons_dir)
    addons.mkdir(parents=True, exist_ok=True)

    # Beside AddOns, so moves are renames on one filesystem and WoW won't list it.
    work = addons.parent / f".ubermoc-install-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    unpacked, previous = work / "new", work / "old"
    previous.mkdir(parents=True)

    moved: list[tuple[Path, Path]] = []
    placed: list[Path] = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(unpacked, [i for i in z.infolist() if len(PurePosixPath(i.filename).parts) > 1 or i.is_dir()])

        leaving = folders + [f for f in (stale or []) if _is_safe_name(f) and "/" not in f]
        for folder in leaving:
            current = _existing(addons, folder)
            if current is not None:
                backup = previous / current.name
                os.replace(current, backup)
                moved.append((backup, current))
        for folder in folders:
            target = addons / folder
            os.replace(unpacked / folder, target)
            placed.append(target)
    except Exception as e:
        for target in placed:
            shutil.rmtree(target, ignore_errors=True)
        for backup, original in moved:
            os.replace(backup, original)
        shutil.rmtree(work, ignore_errors=True)
        if isinstance(e, OSError):
            raise InstallError(f"Couldn't write the addon files: {e}") from e
        raise
    shutil.rmtree(work, ignore_errors=True)
    return folders


def _cmdline(pid: str) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a for a in f.read().decode("utf-8", "replace").split("\0") if a]
    except OSError:
        return []


def game_running(game_folder: str) -> bool:
    """Whether this game's client is running. Unclear cases count as running."""
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return False
    for pid in pids:
        for arg in _cmdline(pid)[:3]:
            if not _WOW_EXE.search(arg):
                continue
            where = _GAME_DIR.search(arg)
            if where is None or where.group(1).lower() == game_folder.lower():
                return True
    return False
