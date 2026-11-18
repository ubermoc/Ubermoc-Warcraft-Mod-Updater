#!/usr/bin/env python3
# Maintainer tool, not shipped. Writes directory.json at the repo root from the collected list.
#   python3 tools/make_directory.py
import json

src = json.load(open("tools/forever_top_ids.json", encoding="utf-8"))
entries = [{"name": a["name"], "source": a["source"], "summary": a.get("summary", "")} for a in src["addons"]]
json.dump({"addons": entries}, open("directory.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"directory.json: {len(entries)} entries")
