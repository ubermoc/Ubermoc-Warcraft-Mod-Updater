# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Find the right release zip for a game on GitHub (or CurseForge).

Most addons publish a release.json with each release, which lists the zip for
every game flavor. It is fetched from github.com rather than api.github.com, so
it doesn't use the 60-an-hour API limit. Only repos without it spend an API call.

A source is written as one of:
- owner/name: the repo's newest release.
- owner/name@prefix: the newest release whose tag starts with "prefix/", for repos that publish several
  things under one releases list (rusty-key/spoken-wow tags "spoken/v3.10.0", "quests-audio/v2.5.0" ...).
- curseforge:12345: the newest release file of that CurseForge project for this game, read from the public
  curseforge.com site (the Project ID is on the addon's CurseForge page).
"""

from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

CA_CANDIDATES = [
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ca-certificates/extracted/tls-ca-bundle.pem",
    "/etc/ssl/cert.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
]
USER_AGENT = "ubermoc-warcraft-mod-updater"
# Voice packs (Spoken's quest pack is about 1.5 GB) are far larger than ordinary addons.
MAX_ZIP_BYTES = 3 * 1024 * 1024 * 1024
MAX_METADATA_BYTES = 5 * 1024 * 1024
_REPO = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+)$")
_PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CURSEFORGE = re.compile(r"^(?:curseforge|cf)\s*:\s*(\d+)$", re.IGNORECASE)
CURSEFORGE_SITE = "https://www.curseforge.com"
# CurseForge's game version type of each flavor (the gameVersionTypeIds on a file).
_CURSEFORGE_FLAVORS = {"mainline": 517, "classic": 67408, "bcc": 73246, "forever": 88568}
_REPO_URL = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s?#]+)", re.IGNORECASE)
# Whole words only: TitanPanel-6.0.zip is an addon's name, not a Titan Reforged build.
_ASSET_WORDS = {
    "classic": "classic",
    "vanilla": "classic",
    "era": "classic",
    "bcc": "bcc",
    "tbc": "bcc",
    "wrath": "wrath",
    "wotlk": "wrath",
    "wotlkc": "wrath",
    "cata": "cata",
    "mists": "mists",
    "mop": "mists",
    "titan": "titan",
    "forever": "forever",
    "camelot": "forever",
    "mainline": "mainline",
    "retail": "mainline",
}


class GitHubError(Exception):
    """A problem to show to the user as it is."""


class NoRelease(GitHubError):
    """The repo exists but offers nothing installable for this game."""


class RateLimited(GitHubError):
    pass


@dataclass
class Release:
    repo: str
    name: str
    version: str
    filename: str
    url: str

    def to_dict(self) -> dict:
        return {"repo": self.repo, "name": self.name, "version": self.version, "filename": self.filename}


def _allowed_host(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (
        host in ("github.com", "api.github.com", "www.curseforge.com", "mediafilez.forgecdn.net", "edge.forgecdn.net")
        or host.endswith(".githubusercontent.com")
    )


class _GitHubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_host(newurl):
            raise GitHubError(f"The download was sent to an unexpected address: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ssl_context() -> ssl.SSLContext:
    for path in CA_CANDIDATES:
        if os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


def _open(url: str, accept: str = "*/*", timeout: float = 20):
    if not _allowed_host(url):
        raise GitHubError(f"Not a GitHub or CurseForge address: {url}")
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_context()), _GitHubRedirects()
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    return opener.open(request, timeout=timeout)


def _read_limited(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise GitHubError("GitHub's reply was larger than expected.")
    expected = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
    if expected and expected.isdigit() and int(expected) != len(data):
        raise _CutOff()
    return data


class _CutOff(OSError):
    """A reply that ended before its stated length (a dropped connection)."""


# One release list per repo is shared by every tag prefix that reads it (Spoken has four), for a few minutes.
_LIST_SECONDS = 5 * 60
_lists: dict[str, tuple[float, object]] = {}
_lists_lock = threading.Lock()


def _api_get(path: str, tries: int = 2):
    try:
        with _open(f"https://api.github.com{path}", accept="application/vnd.github+json") as r:
            return json.loads(_read_limited(r, MAX_METADATA_BYTES).decode("utf-8"))
    except (_CutOff, ValueError) as e:
        if tries > 1:
            return _api_get(path, tries - 1)
        raise GitHubError("GitHub's reply was cut off. Try again.") from e
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and e.headers.get("x-ratelimit-remaining") == "0":
            when = time.strftime("%H:%M", time.localtime(int(e.headers.get("x-ratelimit-reset") or 0)))
            raise RateLimited(f"GitHub's hourly limit was reached. Try again after {when}.") from e
        if e.code == 404:
            return None
        raise GitHubError(f"GitHub answered with error {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GitHubError(f"Could not reach GitHub: {e}") from e


def split_source(source: str) -> tuple[str, str]:
    """(owner/name, tag prefix) of a GitHub source; the prefix is empty for a plain repo."""
    repo, _, prefix = source.partition("@")
    return repo, prefix


def parse_repo(text: str) -> str:
    """A source from what the user typed: owner/name, owner/name@prefix, curseforge:ID, or a link to the repo."""
    text = text.strip()
    cf = _CURSEFORGE.match(text)
    if cf:
        return f"curseforge:{int(cf.group(1))}"
    text, _, prefix = text.partition("@")
    prefix = prefix.strip().strip("/")
    if prefix and not _PREFIX.match(prefix):
        raise GitHubError("After @ put the start of the release tags, for example owner/repo@spoken.")
    text = text.strip()
    match = _REPO_URL.search(text)
    if match:
        owner, name = match.group(1), match.group(2)
        text = f"{owner}/{name[:-4] if name.lower().endswith('.git') else name}"
    text = text.rstrip("/")
    if not _REPO.match(text):
        raise GitHubError("Enter owner/repo, a GitHub link, or curseforge: and the project ID.")
    return f"{text}@{prefix}" if prefix else text


def _download_url(repo: str, filename: str) -> str:
    return f"https://github.com/{repo}/releases/latest/download/{urllib.parse.quote(filename)}"


def _fetch_release_json(repo: str) -> dict | None:
    try:
        with _open(_download_url(repo, "release.json")) as r:
            return json.loads(_read_limited(r, MAX_METADATA_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise GitHubError(f"GitHub answered with error {e.code}.") from e
    except ValueError:
        return None  # malformed metadata: the release's zips can still be used
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GitHubError(f"Could not reach GitHub: {e}") from e


def pick_from_metadata(meta: dict, flavor: str) -> dict | None:
    entries = [e for e in meta.get("releases", []) if not e.get("nolib") and e.get("filename")]

    def matching(wanted: str) -> dict | None:
        return next((e for e in entries if any(m.get("flavor") == wanted for m in e.get("metadata", []))), None)

    entry = matching(flavor) if flavor else (entries[0] if entries else None)
    if entry is None and flavor == "titan":
        entry = matching("wrath")  # the packager also files Titan builds under Wrath
    return entry


def asset_flavor(name: str) -> str:
    for word in re.split(r"[-_.\s]+", name.lower()):
        if word in _ASSET_WORDS:
            return _ASSET_WORDS[word]
    return ""


def pick_asset(assets: list[dict], flavor: str) -> dict | None:
    """The zip for a game: one named for it, else one naming no game at all."""
    zips = [
        a
        for a in assets
        if a.get("name", "").lower().endswith(".zip") and "-nolib" not in a.get("name", "").lower()
    ]
    named = [a for a in zips if flavor and asset_flavor(a["name"]) == flavor]
    general = [a for a in zips if not asset_flavor(a["name"])]
    if not flavor and not general:
        general = zips
    candidates = named or general
    return min(candidates, key=lambda a: len(a["name"])) if candidates else None


def _lookup_by_api(repo: str, flavor: str, prefix: str = "") -> Release:
    # A prefix's newest release can sit behind many others in a shared list, so look further.
    if prefix:
        path = f"/repos/{repo}/releases?per_page=100"
        with _lists_lock:   # also makes the prefixes of one repo wait for a single download
            cached = _lists.get(path.lower())
            if cached and time.time() - cached[0] < _LIST_SECONDS:
                releases = cached[1]
            else:
                releases = _api_get(path)
                _lists[path.lower()] = (time.time(), releases)
    else:
        releases = _api_get(f"/repos/{repo}/releases?per_page=10")
    if releases is None:
        raise GitHubError(f"{repo} wasn't found on GitHub.")
    releases = [r for r in releases if not r.get("draft")]
    if prefix:
        start = f"{prefix.lower()}/"
        releases = [r for r in releases if r.get("tag_name", "").lower().startswith(start)]
        if not releases:
            raise NoRelease(f"{repo} has no releases tagged {prefix}/...")
    stable = [r for r in releases if not r.get("prerelease")]
    release = (stable or releases or [None])[0]
    if release is None:
        raise NoRelease(f"{repo} has no releases to install.")
    asset = pick_asset(release.get("assets", []), flavor)
    if asset is None:
        raise NoRelease(f"{repo} has no installable release for this game.")
    tag = release.get("tag_name", "")
    return Release(
        repo=f"{repo}@{prefix}" if prefix else repo,
        name=prefix or repo.split("/")[1],
        version=tag[len(prefix) + 1:] if prefix else tag,
        filename=asset["name"],
        url=asset["browser_download_url"],
    )


def _site_get(path: str):
    """JSON from curseforge.com's own site API (no key needed)."""
    try:
        with _open(f"{CURSEFORGE_SITE}{path}", accept="application/json") as r:
            return json.loads(_read_limited(r, MAX_METADATA_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise GitHubError(f"CurseForge answered with error {e.code}.") from e
    except ValueError as e:
        raise GitHubError("CurseForge sent something that isn't a file list.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GitHubError(f"Could not reach CurseForge: {e}") from e


def file_version(name: str) -> str:
    """The version in a file's name: "ForeverGraphicsEnhanced v0.9.0.zip" -> "0.9.0"."""
    match = re.search(r"\d+(?:\.\d+)+(?:-[A-Za-z0-9.]+)?", name)
    return match.group(0) if match else name


def pick_curseforge_file(files: list[dict], flavor: str) -> dict | None:
    """The newest release-type file for this game; files are listed newest first."""
    wanted = _CURSEFORGE_FLAVORS.get(flavor)
    for f in files:
        if f.get("releaseType") != 1 or not str(f.get("fileName", "")).lower().endswith(".zip"):
            continue
        if wanted is None or wanted in (f.get("gameVersionTypeIds") or []):
            return f
    return None


def _lookup_curseforge(project: str, flavor: str) -> Release:
    data = _site_get(f"/api/v1/mods/{project}/files?pageIndex=0&pageSize=50&sort=dateCreated&sortDescending=true")
    if data is None:
        raise GitHubError(f"CurseForge has no project {project}.")
    chosen = pick_curseforge_file(data.get("data") or [], flavor)
    if chosen is None:
        raise NoRelease(f"CurseForge project {project} has no release for this game.")
    return Release(
        repo=f"curseforge:{project}",
        name=str(chosen.get("displayName") or chosen.get("fileName")).removesuffix(".zip"),
        version=file_version(str(chosen.get("displayName") or chosen.get("fileName"))),
        filename=chosen["fileName"],
        url=f"{CURSEFORGE_SITE}/api/v1/mods/{project}/files/{int(chosen['id'])}/download",
    )


def lookup(source: str, flavor: str) -> Release:
    if source.lower().startswith("curseforge:"):
        return _lookup_curseforge(source.split(":", 1)[1], flavor)
    repo, prefix = split_source(source)
    if prefix:
        return _lookup_by_api(repo, flavor, prefix)   # release.json belongs to the repo's newest release
    meta = _fetch_release_json(repo)
    if meta is None:
        return _lookup_by_api(repo, flavor)
    entry = pick_from_metadata(meta, flavor)
    if entry is None:
        raise NoRelease(f"{repo} has no release for this game.")
    return Release(
        repo=repo,
        name=entry.get("name") or repo.split("/")[1],
        version=entry.get("version", ""),
        filename=entry["filename"],
        url=_download_url(repo, entry["filename"]),
    )


def latest_release(repo: str) -> dict | None:
    """The newest stable release, for the plugin's own update check."""
    return _api_get(f"/repos/{repo}/releases/latest")


def download(url: str, dest: str, limit: int = MAX_ZIP_BYTES) -> None:
    try:
        with _open(url, timeout=120) as r, open(dest, "wb") as out:
            expected = r.headers.get("Content-Length")
            written = 0
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise GitHubError("The download is larger than the size limit.")
                out.write(chunk)
    except urllib.error.HTTPError as e:
        raise GitHubError(f"Download failed with error {e.code}.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GitHubError(f"Download failed: {e}") from e
    if expected and int(expected) != written:
        raise GitHubError("The download was cut off. Try again.")
