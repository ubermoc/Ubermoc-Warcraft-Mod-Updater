# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Saved GitHub links. Lives in Decky's settings folder, so plugin updates keep it."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

# Repos that moved. Saved links to the old name are rewritten when the file is read.
RENAMED_REPOS = {"ubermoc/ubermocui": "ubermoc/Ubermoc-UI"}


class Store:
    def __init__(self, settings_dir: str | Path):
        self.path = Path(settings_dir) / "links.json"
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"games": {}}
        except (OSError, ValueError):
            # Keep a damaged file for inspection rather than overwriting it.
            try:
                os.replace(self.path, self.path.with_suffix(".bad"))
            except OSError:
                pass
            return {"games": {}}
        if not isinstance(data.get("games"), dict):
            return {"games": {}}
        if self._migrate(data):
            try:
                self._save(data)
            except OSError:
                pass
        return data

    @staticmethod
    def _migrate(data: dict) -> bool:
        changed = False
        for links in data["games"].values():
            for link in links.values() if isinstance(links, dict) else ():
                new = RENAMED_REPOS.get(str(link.get("repo", "")).lower()) if isinstance(link, dict) else None
                if new:
                    link["repo"] = new
                    changed = True
        return changed

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def links(self, game_id: str) -> dict[str, dict]:
        with self._lock:
            return self._load()["games"].get(game_id, {})

    def set_link(self, game_id: str, key: str, link: dict) -> None:
        with self._lock:
            data = self._load()
            data["games"].setdefault(game_id, {})[key] = link
            self._save(data)

    def shortcut(self, game_id: str) -> int:
        """The Steam shortcut made to play this game, or 0."""
        with self._lock:
            value = self._load().get("shortcuts", {}).get(game_id, 0)
            return value if isinstance(value, int) else 0

    def set_shortcut(self, game_id: str, appid: int) -> None:
        with self._lock:
            data = self._load()
            data.setdefault("shortcuts", {})[game_id] = appid
            self._save(data)

    def is_dismissed(self, game_id: str) -> bool:
        with self._lock:
            return game_id in self._load().get("dismissed", [])

    def dismiss(self, game_id: str) -> None:
        with self._lock:
            data = self._load()
            dismissed = data.setdefault("dismissed", [])
            if game_id not in dismissed:
                dismissed.append(game_id)
                self._save(data)

    def remove_link(self, game_id: str, key: str) -> bool:
        with self._lock:
            data = self._load()
            game = data["games"].get(game_id, {})
            if key not in game:
                return False
            del game[key]
            self._save(data)
            return True
