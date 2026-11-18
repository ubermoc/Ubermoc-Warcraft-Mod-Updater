#!/usr/bin/env python3
# Maintainer tool, not shipped. CI check for directory.json changes (C4).
#   python3 tools/check_directory.py <file> [--offline]
# Offline mode skips the live existence checks; CI runs the full check.
import json
import sys

sys.path.insert(0, "py_modules")
from ubermoc_wow import directory, github  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--offline"]
    offline = "--offline" in sys.argv[1:]
    path = args[0] if args else "directory.json"
    raw = json.load(open(path, encoding="utf-8"))
    entries = directory.validate(raw)
    sources = [e["source"] for e in entries]
    dups = sorted({s for s in sources if sources.count(s) > 1})
    if dups:
        print(f"duplicate sources: {dups}")
        return 1
    if offline:
        print(f"OK ({len(entries)} entries), existence not checked")
        return 0
    missing = []
    for e in entries:
        if e["source"].startswith("curseforge:"):
            data = github._site_get(f"/api/v1/mods/{e['source'].split(':', 1)[1]}/files?pageIndex=0&pageSize=1")
            if not data or not data.get("data"):
                missing.append(e["source"])
        elif github._api_get(f"/repos/{e['source']}") is None:
            missing.append(e["source"])
    if missing:
        print(f"not found: {missing}")
        return 1
    print(f"OK ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
