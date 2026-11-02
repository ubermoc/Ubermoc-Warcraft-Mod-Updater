# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Find World of Warcraft games inside Steam's Proton prefixes.

A game is identified from Blizzard's own files, not from folder names:
  <game folder>/.flavor.info   the product code, such as wow or wowf
  <wow root>/.build.info       the installed version of each product
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

_STEAM_ROOTS = (
    ".local/share/Steam",
    ".steam/steam",
    ".steam/root",
    ".var/app/com.valve.Steam/.local/share/Steam",
)
_WOW_SUBPATHS = (
    "drive_c/Program Files (x86)/World of Warcraft",
    "drive_c/Program Files/World of Warcraft",
)
_PRODUCT_DB = "drive_c/ProgramData/Battle.net/Agent/product.db"
_LIBRARY_PATH = re.compile(r'"path"\s+"([^"]+)"')
_GAME_DIR = re.compile(r"^_[a-z0-9_]+_$")
_WINDOWS_PATH = re.compile(rb"[A-Za-z]:/")

# Classic clients by major.minor, from Blizzard's version numbers.
_CLASSIC_LABELS = {
    "1.15": "Classic Era",
    "2.5": "Burning Crusade Classic",
    "3.4": "Wrath Classic",
    "3.80": "Titan Reforged",
    "4.4": "Cataclysm Classic",
    "5.5": "Mists Classic",
}
_RETAIL_LABELS = {12: "Midnight"}
_FOLDER_LABELS = {"_anniversary_": "Classic Anniversary"}
_FLAVORS_BY_THOUSANDS = {
    11: "classic",
    16: "forever",
    20: "bcc",
    30: "wrath",
    40: "cata",
    50: "mists",
}


@dataclass
class Game:
    id: str
    label: str
    folder: str  # e.g. _retail_
    product: str  # e.g. wow
    version: str  # e.g. 12.1.5.70688
    interface: int  # e.g. 120105
    flavor: str  # the BigWigs packager's name, e.g. mainline
    path: str
    addons_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def library_dirs(home: Path) -> list[Path]:
    """Steam library folders (internal drive, SD card, ...), deduplicated."""
    libs: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            real = os.path.realpath(path)
            if real not in seen and path.is_dir():
                seen.add(real)
                libs.append(path)
        except OSError:
            pass

    for sub in _STEAM_ROOTS:
        root = home / sub
        add(root)
        try:
            text = (root / "steamapps" / "libraryfolders.vdf").read_text(errors="replace")
        except OSError:
            continue
        for match in _LIBRARY_PATH.findall(text):
            add(Path(match.replace("\\\\", "\\")))
    return libs


def product_db_paths(data: bytes) -> list[str]:
    """Install paths from Battle.net's product.db.

    It is a protobuf file, so a printable field can follow a path directly. The
    length byte in front of each path says exactly where the path ends.
    """
    found: list[str] = []
    for match in _WINDOWS_PATH.finditer(data):
        start = match.start()
        lengths = []
        if start >= 1 and data[start - 1] < 0x80:
            lengths.append(data[start - 1])
        if start >= 2 and data[start - 2] >= 0x80 and data[start - 1] < 0x80:
            lengths.append((data[start - 2] & 0x7F) | (data[start - 1] << 7))
        for length in lengths:
            raw = data[start : start + length]
            if len(raw) != length or length < 4:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if text.isprintable() and text not in found:
                found.append(text)
                break
    return found


def windows_to_host(pfx: Path, path: str) -> Path:
    """Map a Windows path to the Linux path through the prefix's drive links."""
    drive, rest = path[0].lower(), path[3:]
    return pfx / "dosdevices" / f"{drive}:" / rest


def wow_roots(home: Path) -> list[Path]:
    """Every World of Warcraft folder reachable from a Proton prefix."""
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            real = os.path.realpath(path)
            if real not in seen and (path / ".build.info").is_file():
                seen.add(real)
                roots.append(path)
        except OSError:
            pass

    for lib in library_dirs(home):
        try:
            prefixes = sorted((lib / "steamapps" / "compatdata").iterdir())
        except OSError:
            continue
        for prefix in prefixes:
            pfx = prefix / "pfx"
            for sub in _WOW_SUBPATHS:
                add(pfx / sub)
            try:
                db = (pfx / _PRODUCT_DB).read_bytes()
            except OSError:
                continue
            for path in product_db_paths(db):
                add(windows_to_host(pfx, path))
    return roots


def parse_build_info(text: str) -> dict[str, str]:
    """Product code -> version, from the active rows of .build.info."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return {}
    names = [cell.split("!")[0] for cell in lines[0].split("|")]
    versions: dict[str, str] = {}
    for line in lines[1:]:
        row = dict(zip(names, line.split("|")))
        product, version = row.get("Product", ""), row.get("Version", "")
        if product and version and row.get("Active", "1") == "1":
            versions[product] = version
    return versions


def parse_flavor_info(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[1] if len(lines) >= 2 else ""


def version_to_interface(version: str) -> int:
    """12.1.5.70688 -> 120105, the number addons list in their TOC files."""
    parts = version.split(".")
    try:
        return int(parts[0]) * 10000 + int(parts[1]) * 100 + int(parts[2])
    except (IndexError, ValueError):
        return 0


def flavor_for(product: str, interface: int) -> str:
    """The packager's flavor name, using the same number ranges it does."""
    if product == "wowf":
        return "forever"
    if not interface:
        return ""
    if 38000 <= interface < 39000:
        return "titan"
    return _FLAVORS_BY_THOUSANDS.get(interface // 1000, "mainline")


def label_for(folder: str, product: str, version: str) -> str:
    tag = " PTR" if "ptr" in folder else " Beta" if "beta" in folder else ""
    if product.startswith("wowf"):
        return "Forever" + tag
    if folder in _FOLDER_LABELS:
        return _FOLDER_LABELS[folder] + tag
    parts = version.split(".")
    major_minor = ".".join(parts[:2])
    if major_minor in _CLASSIC_LABELS and "classic" in product + folder:
        return _CLASSIC_LABELS[major_minor] + tag
    if folder in ("_retail_", "_ptr_", "_xptr_", "_beta_") and parts[0].isdigit():
        known = _RETAIL_LABELS.get(int(parts[0]))
        if known:
            return known + tag
    return folder.strip("_").replace("_", " ").title() or folder


def _is_game_dir(path: Path) -> bool:
    if (path / ".flavor.info").is_file():
        return True
    if not _GAME_DIR.match(path.name):
        return False
    try:
        return any(p.name.lower().startswith("wow") and p.suffix.lower() == ".exe" for p in path.iterdir())
    except OSError:
        return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def games_in_root(root: Path) -> list[Game]:
    versions = parse_build_info(_read_text(root / ".build.info"))
    games: list[Game] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return games
    for entry in entries:
        try:
            if not entry.is_dir() or not _is_game_dir(entry):
                continue
        except OSError:
            continue
        product = parse_flavor_info(_read_text(entry / ".flavor.info"))
        version = versions.get(product, "")
        interface = version_to_interface(version)
        real = os.path.realpath(entry)
        games.append(
            Game(
                id=hashlib.sha1(real.encode()).hexdigest()[:12],
                label=label_for(entry.name, product, version),
                folder=entry.name,
                product=product,
                version=version,
                interface=interface,
                flavor=flavor_for(product, interface),
                path=str(entry),
                addons_path=str(entry / "Interface" / "AddOns"),
            )
        )
    return games


def find_games(home: Path) -> list[Game]:
    games: list[Game] = []
    for root in wow_roots(home):
        games.extend(games_in_root(root))
    # Newest client first: Midnight, then Forever, then Classic.
    games.sort(key=lambda g: (-g.interface, g.label))
    return games
