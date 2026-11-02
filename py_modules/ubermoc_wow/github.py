# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Find the right release zip for a game on GitHub.

Most addons publish a release.json with each release, which lists the zip for
every game flavor. It is fetched from github.com rather than api.github.com, so
it doesn't use the 60-an-hour API limit. Only repos without it spend an API call.
"""

from __future__ import annotations

import json
import os
import re
import ssl
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
MAX_ZIP_BYTES = 300 * 1024 * 1024
MAX_METADATA_BYTES = 5 * 1024 * 1024
_REPO = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+)$")
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
        host in ("github.com", "api.github.com") or host.endswith(".githubusercontent.com")
    )


class _GitHubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_host(newurl):
            raise GitHubError(f"GitHub sent a download to an unexpected address: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ssl_context() -> ssl.SSLContext:
    for path in CA_CANDIDATES:
        if os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


def _open(url: str, accept: str = "*/*", timeout: float = 20):
    if not _allowed_host(url):
        raise GitHubError(f"Not a GitHub address: {url}")
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_context()), _GitHubRedirects()
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    return opener.open(request, timeout=timeout)


def _read_limited(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise GitHubError("GitHub's reply was larger than expected.")
    return data


def _api_get(path: str):
    try:
        with _open(f"https://api.github.com{path}", accept="application/vnd.github+json") as r:
            return json.loads(_read_limited(r, MAX_METADATA_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and e.headers.get("x-ratelimit-remaining") == "0":
            when = time.strftime("%H:%M", time.localtime(int(e.headers.get("x-ratelimit-reset") or 0)))
            raise RateLimited(f"GitHub's hourly limit was reached. Try again after {when}.") from e
        if e.code == 404:
            return None
        raise GitHubError(f"GitHub answered with error {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GitHubError(f"Could not reach GitHub: {e}") from e


def parse_repo(text: str) -> str:
    """owner/name from what the user typed: owner/name or any link to the repo."""
    text = text.strip()
    match = _REPO_URL.search(text)
    if match:
        owner, name = match.group(1), match.group(2)
        text = f"{owner}/{name[:-4] if name.lower().endswith('.git') else name}"
    text = text.rstrip("/")
    if not _REPO.match(text):
        raise GitHubError("Enter owner/repo or a GitHub link.")
    return text


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


def _lookup_by_api(repo: str, flavor: str) -> Release:
    releases = _api_get(f"/repos/{repo}/releases?per_page=10")
    if releases is None:
        raise GitHubError(f"{repo} wasn't found on GitHub.")
    releases = [r for r in releases if not r.get("draft")]
    stable = [r for r in releases if not r.get("prerelease")]
    release = (stable or releases or [None])[0]
    if release is None:
        raise NoRelease(f"{repo} has no releases to install.")
    asset = pick_asset(release.get("assets", []), flavor)
    if asset is None:
        raise NoRelease(f"{repo} has no installable release for this game.")
    return Release(
        repo=repo,
        name=repo.split("/")[1],
        version=release.get("tag_name", ""),
        filename=asset["name"],
        url=asset["browser_download_url"],
    )


def lookup(repo: str, flavor: str) -> Release:
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
