#!/usr/bin/env python3
# Maintainer tool, not shipped in the plugin zip. Turns slugs into CurseForge project IDs with the
# official API and your own free key (console.curseforge.com), read from the CF_API_KEY variable.
#   CF_API_KEY=... python3 tools/resolve_ids.py tools/forever_top_slugs.json tools/forever_top_ids.json
import json, os, sys, time, urllib.parse, urllib.request

key = os.environ.get("CF_API_KEY", "")
if not key or len(sys.argv) != 3:
    sys.exit("Set CF_API_KEY and pass: input.json output.json")
src = json.load(open(sys.argv[1], encoding="utf-8"))
out, missing = [], []
for item in src["addons"]:
    url = "https://api.curseforge.com/v1/mods/search?" + urllib.parse.urlencode({"gameId": 1, "slug": item["slug"]})
    req = urllib.request.Request(url, headers={"x-api-key": key, "Accept": "application/json", "User-Agent": "ubermoc-warcraft-mod-updater-tools"})
    with urllib.request.urlopen(req, timeout=20) as r:
        hits = [m for m in json.load(r).get("data", []) if m.get("slug") == item["slug"]]
    if hits:
        out.append({"name": item["name"], "slug": item["slug"], "source": f"curseforge:{hits[0]['id']}"})
    else:
        missing.append(item["slug"])
    time.sleep(0.5)  # polite pace
json.dump({**{k: v for k, v in src.items() if k != "addons"}, "addons": out}, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
print(f"resolved {len(out)}, missing {len(missing)}: {missing}")
