#!/usr/bin/env python3
# Maintainer tool, not shipped. Adds summaries to the directory file.
#   python3 tools/merge_summaries.py tools/summaries_done.json
# summaries_done.json is {"slug": "one-sentence summary", ...} from the local model.
import json, sys
done = json.load(open(sys.argv[1], encoding="utf-8"))
path = "tools/forever_top_ids.json"
data = json.load(open(path, encoding="utf-8"))
added = 0
for a in data["addons"]:
    text = str(done.get(a["slug"], "")).strip()
    if text and not a.get("summary"):
        a["summary"] = text
        added += 1
json.dump(data, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
left = [a["slug"] for a in data["addons"] if not a.get("summary")]
print(f"added {added}, still missing {len(left)}: {left}")
