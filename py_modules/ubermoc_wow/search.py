# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Fuzzy look-up of addons by name: the built-in catalog, plus CurseForge when the person has saved an API key."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

MIN_SCORE = 0.55
MAX_RESULTS = 8


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def score(query: str, name: str) -> float:
    """0 to 1. Typos, missing spaces, a part of the name and word order all still match."""
    q, n = _norm(query), _norm(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if q in n:
        return 0.85 + 0.1 * len(q) / len(n)
    best = SequenceMatcher(None, q, n).ratio()
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if len(w) > 2]
    query_words = [w for w in re.split(r"[^a-z0-9]+", query.lower()) if len(w) > 2]
    for w in words:
        for qw in query_words:
            best = max(best, 0.9 * SequenceMatcher(None, qw, w).ratio())
    return best


def search_catalog(query: str, catalog: dict[str, str]) -> list[dict]:
    """catalog is lowercase folder -> source. Folders that share one source are one result."""
    by_source: dict[str, tuple[float, str]] = {}
    for folder, source in catalog.items():
        s = score(query, folder)
        if s < MIN_SCORE:
            continue
        old = by_source.get(source)
        if old is None or (s, -len(folder)) > (old[0], -len(old[1])):
            by_source[source] = (s, folder)
    return [{"title": folder, "source": source, "detail": source, "origin": "catalog", "score": s} for source, (s, folder) in by_source.items()]


def search_directory(query: str, entries: list[dict]) -> list[dict]:
    """The published directory. A name match wins; a summary-only match ranks lower."""
    results = []
    for e in entries:
        s = max(score(query, e["name"]), 0.7 * score(query, e["summary"]))
        if s < MIN_SCORE:
            continue
        results.append({"title": e["name"], "source": e["source"], "detail": e["summary"] or e["source"], "origin": "directory", "score": s})
    return results


def search_curseforge_results(query: str, mods: list[dict]) -> list[dict]:
    results = []
    for m in mods:
        s = max(score(query, m["name"]), 0.5)  # CurseForge already matched it; fuzzy only orders them
        detail = m["summary"][:80] or f"{m['downloads']:,} downloads"
        results.append({"title": m["name"], "source": f"curseforge:{m['id']}", "detail": detail, "origin": "curseforge", "score": s})
    return results


def merge(*lists: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for item in (i for group in lists for i in group):
        old = best.get(item["source"].lower())
        if old is None or item["score"] > old["score"]:
            best[item["source"].lower()] = item
    ranked = sorted(best.values(), key=lambda i: (-i["score"], i["title"].lower()))[:MAX_RESULTS]
    return [{k: v for k, v in i.items() if k != "score"} for i in ranked]
