# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""The addon directory: a list the maintainer publishes as directory.json at the repo root.

Read-only for the plugin. It is fetched over HTTPS from raw.githubusercontent.com
(C1; the URL is checked by `github._allowed_host` as usual, C2), cached in the
settings folder, and the last good copy is kept when a download is bad or missing.
The copy shipped inside the plugin folder is the offline fallback. Nothing here can
change the repo; suggestions go through a prefilled GitHub issue (see service.suggest_issue).

Two lists are used together: the public one above, and the person's own, `directory.local.json` in the
settings folder. The own list never leaves the device, is never published, and is read with the same strict
validation; a bad or missing one is ignored. A source in both lists is shown once (the public entry wins).

The published file must be a JSON object:
  {"addons": [{"name": "...", "source": "curseforge:<digits> or owner/repo", "summary": "..."}]}
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import github

MAX_BYTES = 200_000      # the published file is about 15 KB; anything larger is not this list
MAX_ENTRIES = 400
MAX_NAME = 100
MAX_SUMMARY = 200
CACHE_SECONDS = 15 * 60


def validate(raw) -> list[dict]:
    """Strictly validate one directory file and return clean entries. Raises GitHubError on anything else."""
    if not isinstance(raw, dict):
        raise github.GitHubError("The directory is not a JSON object.")
    items = raw.get("addons")
    if not isinstance(items, list) or len(items) > MAX_ENTRIES:
        raise github.GitHubError("The directory does not have a list of addons.")
    entries = []
    for item in items:
        if not isinstance(item, dict):
            raise github.GitHubError("A directory entry is not an object.")
        name, source, summary = item.get("name"), item.get("source"), item.get("summary")
        if not isinstance(name, str) or not 0 < len(name) <= MAX_NAME:
            raise github.GitHubError("A directory entry has a name of the wrong size.")
        # exactly curseforge:<digits> or owner/repo; prefixes belong to the catalog, not the directory
        if not isinstance(source, str) or "@" in source or source != github.parse_repo(source):
            raise github.GitHubError(f"A directory entry has a source that isn't curseforge:<digits> or owner/repo: {source!r}")
        if not isinstance(summary, str) or len(summary) > MAX_SUMMARY:
            raise github.GitHubError("A directory entry has a summary of the wrong size.")
        entries.append({"name": name, "source": source, "summary": summary})
    return entries


class Directory:
    def __init__(self, settings_dir, plugin_dir, repo: str, logger=None, fetch=None):
        self.settings_path = Path(settings_dir) / "directory.json"
        self.plugin_path = Path(plugin_dir) / "directory.json"
        self.local_path = Path(settings_dir) / "directory.local.json"
        self.url = f"https://raw.githubusercontent.com/{repo}/main/directory.json"
        # FAKE(C1): raw.githubusercontent.com replies with the repo-root JSON file itself.
        self._fetch = fetch
        self.logger = logger
        self._lock = threading.Lock()
        self._last_try = 0.0

    def entries(self) -> list[dict]:
        """The public list, then the person's own entries whose source is not already in it. Never raises."""
        public = self._public_entries()
        seen = {e["source"] for e in public}
        return public + [e for e in self._local_entries() if e["source"] not in seen]

    def _local_entries(self) -> list[dict]:
        try:
            return validate(json.loads(self.local_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, github.GitHubError):
            return []

    def _public_entries(self) -> list[dict]:
        """The best public copy available: fresh cache, else a download, else the last good copy, else the shipped one."""
        with self._lock:
            cache = self._read_cache()
            if cache is not None and time.time() - cache[0] < CACHE_SECONDS:
                return cache[1]
            if time.time() - self._last_try >= CACHE_SECONDS:
                self._last_try = time.time()
                try:
                    fresh = validate(self._download())
                except (github.GitHubError, ValueError, OSError) as e:
                    if self.logger:
                        self.logger.info(f"directory: {e}; keeping the last good copy")
                else:
                    try:
                        self._write_cache(fresh)
                    except OSError:
                        pass
                    return fresh
            if cache is not None:
                return cache[1]
            try:
                return validate(json.loads(self.plugin_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, github.GitHubError):
                return []

    def _download(self):
        if self._fetch is not None:
            return self._fetch()
        with github._open(self.url, accept="application/json") as r:
            return json.loads(github._read_limited(r, MAX_BYTES).decode("utf-8"))

    def _read_cache(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("cached"), (int, float)) or not isinstance(data.get("addons"), list):
            return None
        try:
            return data["cached"], validate(data)
        except github.GitHubError:
            return None

    def _write_cache(self, entries: list[dict]) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cached": time.time(), "addons": entries}, indent=1), encoding="utf-8")
        tmp.replace(self.settings_path)
