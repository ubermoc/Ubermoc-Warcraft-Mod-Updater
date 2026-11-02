# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Read installed addons from their TOC files and group them into rows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# The client tries the game's own suffixes, then the family, then the plain file.
# https://warcraft.wiki.gg/wiki/TOC_format
_TOC_SUFFIXES = {
    "mainline": ("Standard", "Mainline"),
    "forever": ("Forever", "Camelot", "Mainline"),
    "classic": ("Vanilla", "Classic"),
    "bcc": ("TBC", "BCC", "Classic"),
    "wrath": ("Wrath", "WOTLKC", "Classic"),
    "titan": ("Wrath", "WOTLKC", "Classic"),
    "cata": ("Cata", "Classic"),
    "mists": ("Mists", "Classic"),
}
_ANY_SUFFIX = tuple(dict.fromkeys(s for group in _TOC_SUFFIXES.values() for s in group))
_META = re.compile(r"^\s*##\s*([^:]+?)\s*:\s*(.*?)\s*$")
_COLOR_CODES = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T[^|]*\|t|\|A[^|]*\|a|\|n")
_GITHUB_URL = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+)", re.IGNORECASE)
_NOT_OWNERS = {"orgs", "sponsors", "users", "settings", "marketplace", "topics"}
_PROJECT_IDS = ("x-curse-project-id", "x-wago-id", "x-wowi-id")
PLACEHOLDER = "@project-version@"


@dataclass
class Addon:
    folder: str
    title: str
    version: str = ""
    repo: str = ""  # owner/name from an X- field
    ids: list[str] = field(default_factory=list)


@dataclass
class Row:
    """One entry in the panel: an addon and any folders that belong to it."""

    key: str  # main folder, which also names the saved link
    title: str
    folders: list[str]
    version: str
    repo: str
    source: str  # link, toc, catalog or empty

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "folders": self.folders,
            "version": self.version,
            "repo": self.repo,
            "source": self.source,
        }


def parse_toc(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        match = _META.match(line)
        if match:
            meta.setdefault(match.group(1).lower(), match.group(2))
    return meta


def clean_title(title: str) -> str:
    return " ".join(_COLOR_CODES.sub("", title).split())


def repo_from_url(text: str) -> str:
    """owner/name from a full repo URL. An organization page has no repo in it."""
    match = _GITHUB_URL.search(text)
    if not match or match.group(1).lower() in _NOT_OWNERS:
        return ""
    name = match.group(2)
    if name.lower().endswith(".git"):
        name = name[:-4]
    return f"{match.group(1)}/{name}" if name else ""


def toc_name_matches(folder: str, filename: str) -> bool:
    """WoW only loads a TOC named after its folder, with an optional client suffix."""
    lower = filename.lower()
    base = folder.lower()
    if lower == f"{base}.toc":
        return True
    return any(lower == f"{base}{sep}{suffix.lower()}.toc" for suffix in _ANY_SUFFIX for sep in "_-")


def find_toc(path: Path, flavor: str) -> Path | None:
    try:
        files = {p.name.lower(): p for p in path.iterdir() if p.is_file()}
    except OSError:
        return None
    base = path.name.lower()
    for suffix in _TOC_SUFFIXES.get(flavor, ()):
        for sep in "_-":
            found = files.get(f"{base}{sep}{suffix.lower()}.toc")
            if found:
                return found
    plain = files.get(f"{base}.toc")
    if plain:
        return plain
    # The client wouldn't load this one, but it is still an addon on disk.
    matching = sorted(name for name in files if toc_name_matches(path.name, name))
    return files[matching[0]] if matching else None


def read_addon(path: Path, flavor: str) -> Addon | None:
    toc = find_toc(path, flavor)
    if toc is None:
        return None
    try:
        meta = parse_toc(toc.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return None
    version = meta.get("version", "")
    repo = ""
    for key, value in meta.items():
        if key.startswith("x-"):
            repo = repo_from_url(value)
            if repo:
                break
    return Addon(
        folder=path.name,
        title=clean_title(meta.get("title", "")) or path.name,
        version="" if version == PLACEHOLDER else version,
        repo=repo,
        ids=[f"{key}={meta[key]}" for key in _PROJECT_IDS if meta.get(key)],
    )


def read_addons(addons_dir: Path, flavor: str) -> list[Addon]:
    try:
        folders = sorted(p for p in addons_dir.iterdir() if p.is_dir())
    except OSError:
        return []
    return [addon for addon in (read_addon(p, flavor) for p in folders) if addon]


def _main_addon(addons: list[Addon]) -> Addon:
    return min(addons, key=lambda a: (len(a.folder), a.folder.lower()))


def _detected_row(group: list[Addon], catalog: dict[str, str]) -> Row:
    main = _main_addon(group)
    ordered = [main] + [a for a in group if a is not main]
    repo = next((a.repo for a in ordered if a.repo), "")
    source = "toc" if repo else ""
    if not repo:
        repo = next((catalog[a.folder.lower()] for a in ordered if a.folder.lower() in catalog), "")
        source = "catalog" if repo else ""
    return Row(main.folder, main.title, [a.folder for a in ordered], main.version, repo, source)


def build_rows(addons: list[Addon], links: dict[str, dict], catalog: dict[str, str]) -> list[Row]:
    """Group folders: saved links first, then shared project IDs, else one row each."""
    by_folder = {a.folder.lower(): a for a in addons}
    used: set[str] = set()
    rows: list[Row] = []

    for key, link in links.items():
        wanted = [key] + [f for f in link.get("folders", []) if f.lower() != key.lower()]
        group = [by_folder[f.lower()] for f in wanted if f.lower() in by_folder and f.lower() not in used]
        if not group:
            continue  # uninstalled by something else; its link has nothing to show
        used.update(a.folder.lower() for a in group)
        main = group[0]
        rows.append(
            Row(key, main.title, [a.folder for a in group], link.get("version") or main.version, link["repo"], "link")
        )

    groups: dict[str, list[Addon]] = {}
    for addon in addons:
        if addon.folder.lower() in used:
            continue
        shared = next((i for i in addon.ids if i in groups), None)
        if shared is None:
            shared = addon.ids[0] if addon.ids else f"folder={addon.folder}"
            groups[shared] = []
        groups[shared].append(addon)
    rows.extend(_detected_row(group, catalog) for group in groups.values())

    # Addons that can update go first.
    rows.sort(key=lambda r: (not r.repo, r.title.lower()))
    return rows
