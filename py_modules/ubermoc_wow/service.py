# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""What the panel can ask for. main.py is a thin async layer over this class."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import discover, github, installer, toc
from .autologin import AutoLogin
from .login import LoginVault
from .store import Store

PLUGIN_NAME = "Ubermoc Warcraft Mod Updater"
PLUGIN_REPO = "ubermoc/Ubermoc-Warcraft-Mod-Updater"
PLUGIN_ASSET = "Ubermoc-Warcraft-Mod-Updater.zip"
PLUGIN_FILES = ("plugin.json", "main.py", "dist/index.js")
# Offered by default. Its TOC only supports the live Midnight and Forever clients.
DEFAULT_ADDONS = (
    {"title": "Ubermoc UI", "folder": "UbermocUI", "repo": "ubermoc/Ubermoc-UI",
     "blurb": "Play World of Warcraft with just a controller."},
    {"title": "Ubermoc Forever", "folder": "UbermocForever", "repo": "ubermoc/Ubermoc-Forever",
     "blurb": "A controller-first interface for Forever and Midnight."},
)
DEFAULT_ADDON_PRODUCTS = ("wow", "wowf")
CACHE_SECONDS = 15 * 60
CHECK_WORKERS = 4


def _same_version(a: str, b: str) -> bool:
    return a.strip().lower().lstrip("v") == b.strip().lower().lstrip("v")


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


class Updater:
    def __init__(self, home: str, settings_dir: str, runtime_dir: str, plugin_dir: str):
        self.home = Path(home)
        self.runtime_dir = Path(runtime_dir)
        self.plugin_dir = Path(plugin_dir)
        self.store = Store(settings_dir)
        self.login = LoginVault(settings_dir)
        self.autologin = AutoLogin(lambda: (self.login.read() or {}).get("password", ""))
        self.catalog = self._load_catalog()
        self._games: list[discover.Game] | None = None
        self._releases: dict[tuple[str, str], tuple[float, object]] = {}
        self._busy = threading.Lock()

    def _load_catalog(self) -> dict[str, str]:
        try:
            data = json.loads((self.plugin_dir / "catalog.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {folder.lower(): repo for folder, repo in data.items()}

    # ---------- games and addons ----------
    def games(self, rescan: bool = False) -> list[discover.Game]:
        if self._games is None or rescan:
            self._games = discover.find_games(self.home)
        return self._games

    def _game(self, game_id: str) -> discover.Game:
        for game in self.games():
            if game.id == game_id:
                return game
        for game in self.games(rescan=True):
            if game.id == game_id:
                return game
        raise github.GitHubError("That game isn't installed any more. Try Rescan.")

    def list_games(self, rescan: bool = False) -> list[dict]:
        return [g.to_dict() for g in self.games(rescan)]

    def login_status(self) -> dict:
        return self.login.status()

    def save_login(self, password: str) -> dict:
        return self.login.save(password)

    def remove_login(self) -> dict:
        return self.login.remove()

    def start_login(self, game_id: str) -> dict:
        """Call just before starting a game: types the saved password into its login screen."""
        game = self._game(game_id)
        return self.autologin.begin(game_id, game.folder, game.path)

    def login_state(self, game_id: str) -> dict:
        return self.autologin.state(game_id)

    def play_info(self, game_id: str) -> dict:
        """What the panel needs to make and start a Steam shortcut for this game."""
        game = self._game(game_id)
        if not game.exe:
            raise github.GitHubError("Play can't find this game's Wow.exe. Install the game with Battle.net in Steam first, then try again.")
        return {
            "name": f"World of Warcraft {game.label}",
            "exe": game.exe,
            "start_dir": game.path,
            "prefix": game.prefix,
            "prefix_appid": game.prefix_appid,
            "shortcut": self.store.shortcut(game_id),
        }

    def save_shortcut(self, game_id: str, appid: int) -> bool:
        self._game(game_id)
        self.store.set_shortcut(game_id, int(appid))
        return True

    def _rows(self, game: discover.Game) -> list[toc.Row]:
        addons = toc.read_addons(Path(game.addons_path), game.flavor)
        return toc.build_rows(addons, self.store.links(game.id), self.catalog)

    def list_addons(self, game_id: str) -> list[dict]:
        return [r.to_dict() for r in self._rows(self._game(game_id))]

    def _row(self, game: discover.Game, key: str) -> toc.Row:
        for row in self._rows(game):
            if row.key == key:
                return row
        raise github.GitHubError("That addon is no longer installed.")

    @staticmethod
    def _dismiss_key(game_id: str, folder: str) -> str:
        # Ubermoc UI keeps the bare game id so earlier "Not now" answers still count.
        return game_id if folder == DEFAULT_ADDONS[0]["folder"] else f"{game_id}:{folder}"

    def default_addons(self, game_id: str) -> list[dict]:
        """The addons to offer for this game, if they should be offered."""
        game = self._game(game_id)
        if game.product not in DEFAULT_ADDON_PRODUCTS:
            return []
        installed = {a.folder.lower() for a in toc.read_addons(Path(game.addons_path), game.flavor)}
        return [
            dict(addon) for addon in DEFAULT_ADDONS
            if addon["folder"].lower() not in installed
            and not self.store.is_dismissed(self._dismiss_key(game_id, addon["folder"]))
        ]

    def dismiss_default_addon(self, game_id: str, folder: str = "UbermocUI") -> bool:
        self._game(game_id)
        self.store.dismiss(self._dismiss_key(game_id, folder))
        return True

    # ---------- GitHub ----------
    def _lookup(self, repo: str, flavor: str, fresh: bool = False) -> github.Release:
        """Releases and "nothing to install" answers are remembered for a while."""
        now = time.time()
        cached = self._releases.get((repo.lower(), flavor))
        if cached and not fresh and now - cached[0] < CACHE_SECONDS:
            if isinstance(cached[1], github.NoRelease):
                raise cached[1]
            return cached[1]
        try:
            release = github.lookup(repo, flavor)
        except github.NoRelease as e:
            self._releases[(repo.lower(), flavor)] = (now, e)
            raise
        self._releases[(repo.lower(), flavor)] = (now, release)
        return release

    def _status(self, game: discover.Game, row: toc.Row, fresh: bool) -> dict:
        try:
            release = self._lookup(row.repo, game.flavor, fresh)
        except github.NoRelease as e:
            return {"state": "unavailable", "message": str(e)}
        except github.GitHubError as e:
            return {"state": "error", "message": str(e)}
        result = {"latest": release.version, "installed": row.version}
        link = self.store.links(game.id).get(row.key, {})
        toc_versions = [a.version for a in self._folder_addons(game, row)]
        known = [v for v in [link.get("version", "")] + toc_versions if v]
        if any(_same_version(v, release.version) for v in known):
            return {**result, "state": "current"}
        if not known:
            return {**result, "state": "unknown"}
        if all(_version_tuple(v) > _version_tuple(release.version) for v in known):
            return {**result, "state": "current"}  # newer than the latest release
        return {**result, "state": "update"}

    def _folder_addons(self, game: discover.Game, row: toc.Row) -> list[toc.Addon]:
        found = (toc.read_addon(Path(game.addons_path) / f, game.flavor) for f in row.folders[:1])
        return [a for a in found if a]

    def check_addons(self, game_id: str, fresh: bool = False) -> dict[str, dict]:
        game = self._game(game_id)
        rows = [r for r in self._rows(game) if r.repo]
        with ThreadPoolExecutor(CHECK_WORKERS) as pool:
            statuses = pool.map(lambda r: self._status(game, r, fresh), rows)
        return {row.key: status for row, status in zip(rows, statuses)}

    def check_repo(self, game_id: str, text: str) -> dict:
        game = self._game(game_id)
        repo = github.parse_repo(text)
        return self._lookup(repo, game.flavor, fresh=True).to_dict()

    # ---------- links ----------
    def save_link(self, game_id: str, key: str, text: str) -> dict:
        game = self._game(game_id)
        repo = github.parse_repo(text)
        release = self._lookup(repo, game.flavor)
        row = self._row(game, key)
        old = self.store.links(game_id).get(key, {})
        # A new repo means the version on disk says nothing about that repo.
        same_repo = old.get("repo", "").lower() == repo.lower()
        self.store.set_link(
            game_id,
            key,
            {
                "repo": repo,
                "folders": row.folders,
                "owned": old.get("owned", []),
                "version": old.get("version", "") if same_repo else "",
            },
        )
        return release.to_dict()

    def remove_link(self, game_id: str, key: str) -> bool:
        self._game(game_id)
        return self.store.remove_link(game_id, key)

    # ---------- installing ----------
    def _install(self, game: discover.Game, repo: str, must_contain: str, old_link: dict) -> tuple[list[str], github.Release]:
        if installer.game_running(game.folder):
            raise installer.InstallError(f"Close {game.label} first. Its addons are in use.")
        if not self._busy.acquire(blocking=False):
            raise installer.InstallError("Another install is still running.")
        try:
            release = self._lookup(repo, game.flavor, fresh=True)
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.runtime_dir, prefix="addon-") as tmp:
                zip_path = os.path.join(tmp, "addon.zip")
                github.download(release.url, zip_path)
                folders = installer.check_zip(zip_path)
                if must_contain and must_contain.lower() not in (f.lower() for f in folders):
                    raise installer.InstallError(
                        f"That release doesn't contain {must_contain}, so nothing was changed. Check the repo."
                    )
                lower = {f.lower() for f in folders}
                stale = [f for f in old_link.get("owned", []) if f.lower() not in lower]
                installer.install_zip(zip_path, game.addons_path, stale)
            return folders, release
        finally:
            self._busy.release()

    def update_addon(self, game_id: str, key: str) -> dict:
        game = self._game(game_id)
        row = self._row(game, key)
        if not row.repo:
            raise github.GitHubError("This addon isn't linked to a GitHub repo yet.")
        old = self.store.links(game_id).get(key, {})
        folders, release = self._install(game, row.repo, key, old)
        self.store.set_link(
            game_id,
            key,
            {"repo": row.repo, "folders": folders, "owned": folders, "version": release.version},
        )
        return {"title": row.title, "version": release.version}

    def add_addon(self, game_id: str, text: str) -> dict:
        game = self._game(game_id)
        repo = github.parse_repo(text)
        links = self.store.links(game_id)
        key = next((k for k, v in links.items() if v.get("repo", "").lower() == repo.lower()), "")
        folders, release = self._install(game, repo, "", links.get(key, {}))
        key = key if key.lower() in (f.lower() for f in folders) else min(folders, key=lambda f: (len(f), f.lower()))
        self.store.set_link(game_id, key, {"repo": repo, "folders": folders, "owned": folders, "version": release.version})
        return {"title": release.name, "version": release.version}

    # ---------- the plugin itself ----------
    def plugin_version(self) -> str:
        try:
            data = json.loads((self.plugin_dir / "package.json").read_text(encoding="utf-8"))
            return data.get("version", "unknown")
        except (OSError, ValueError):
            return "unknown"

    def _plugin_release(self) -> dict | None:
        return github.latest_release(PLUGIN_REPO)

    def check_plugin(self) -> dict:
        current = self.plugin_version()
        release = self._plugin_release()
        if release is None:
            return {"current": current, "latest": "", "available": False, "message": "No release has been published yet."}
        latest = release.get("tag_name", "").lstrip("v")
        return {"current": current, "latest": latest, "available": _version_tuple(latest) > _version_tuple(current)}

    def install_plugin_update(self) -> dict:
        """Download the update, check it, then overwrite this plugin's files in place.

        Nothing is touched until the whole zip is good. The panel then asks Decky to
        reload the plugin, which restarts this backend and loads the new panel.
        """
        release = self._plugin_release()
        if release is None:
            raise github.GitHubError("No release has been published yet.")
        asset = next((a for a in release.get("assets", []) if a.get("name") == PLUGIN_ASSET), None)
        if asset is None:
            raise github.GitHubError("The latest release has no plugin zip.")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        path = self.runtime_dir / PLUGIN_ASSET
        github.download(asset["browser_download_url"], str(path))
        self._check_plugin_zip(path)
        prefix = f"{PLUGIN_NAME}/"
        with zipfile.ZipFile(path) as z:
            members = [m for m in z.infolist() if m.filename.startswith(prefix) and not m.is_dir()]
            try:
                for member in members:
                    dest = self.plugin_dir / member.filename[len(prefix):]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_name(dest.name + ".new")
                    tmp.write_bytes(z.read(member))
                    os.replace(tmp, dest)
            except OSError as e:
                raise github.GitHubError(f"Couldn't write the update: {e}") from e
        return {"version": release.get("tag_name", "").lstrip("v")}

    @staticmethod
    def _check_plugin_zip(path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    raise github.GitHubError("The update download is damaged.")
                names = set(z.namelist())
                plugin_json = z.read(f"{PLUGIN_NAME}/plugin.json")
        except (zipfile.BadZipFile, KeyError, OSError) as e:
            raise github.GitHubError(f"The update isn't a usable plugin zip: {e}") from e
        for name in names:
            if ".." in name.split("/") or name.startswith("/"):
                raise github.GitHubError(f"The update contains an unsafe path: {name}")
        missing = [f for f in PLUGIN_FILES if f"{PLUGIN_NAME}/{f}" not in names]
        if missing:
            raise github.GitHubError(f"The update is missing {missing[0]}.")
        try:
            name = json.loads(plugin_json).get("name")
        except ValueError:
            name = None
        if name != PLUGIN_NAME:
            raise github.GitHubError("The update is for a different plugin.")
