# Handoff: Ubermoc Warcraft Mod Updater

Read `Ubermoc.md` first (the release process and care points). This file is the current state and the
work that remains. The maintainer is Marcos (GitHub: ubermoc). Be plain and direct with him, report
what was verified and what was not, and do not wait on him for things you can do yourself.

## What this is
A Decky Loader plugin (TypeScript panel in `src/`, Python backend in `main.py` + `py_modules/ubermoc_wow/`)
that finds WoW in Steam Proton prefixes and updates addons from GitHub releases and CurseForge in Gaming Mode.

Run the tests: `python3 -m unittest discover -s tests -v` (94 pass).
Typecheck: `npx --no-install tsc --noEmit -p .`  Bundle: `npx --no-install rollup -c`.
`pnpm` is not installed on this machine, so `scripts/package.sh` cannot run here.

## Already built (uncommitted in the working tree)
- Clear saved data for an addon (deletes its SavedVariables from `WTF`, all accounts/characters) and
  Delete (whole addon, or one part of a multi-folder addon, optional "also clear saved data"). Both are
  two-step in the panel and refuse while the game runs. Backend: `savedata.py`, `installer.remove_folders`,
  `Updater.clear_saved_data` / `remove_addon`. UI: `src/AddonItem.tsx`. The old "Remove" button is now "Unlink".
- Fuzzy name search: `search.py` (catalog now; CurseForge when the person saves their own API key in the
  "CurseForge search" panel section, `src/CurseForgeKey.tsx`). `Updater.search_addons`. UI: "Find by name" in
  `src/RepoEditor.tsx`.
- An unlinked addon whose TOC has `X-Curse-Project-ID` is offered `curseforge:ID` (`Row.suggestion`).
- README updated for the above.

## Data collected (in `tools/`, not shipped in the plugin zip)
- `forever_top_ids.json`: the top 100 WoW **Forever** addons by downloads (as of 2026-11-18), each with
  `name`, `slug`, `source` (`curseforge:ID`, read from each project page's "Project ID") and `summary`
  (the one-sentence summary under the addon's name). 48 summaries are filled; 52 are empty.
- `summaries_todo.json`: the 52 addons still needing a summary. `LOCAL_MODEL_PROMPT.md` is the prompt for that.
  `merge_summaries.py` merges a `{slug: summary}` JSON file back in.
- `resolve_ids.py`: turns slugs into IDs with the official API and `CF_API_KEY`. Not run; the maintainer has
  no key yet.

## Remaining work, in order
1. **Finish the 52 summaries** (see `LOCAL_MODEL_PROMPT.md`), then run `merge_summaries.py`. This needs a
   browser tool connected to the maintainer's Chrome. If you have none, skip to step 2 and say so; the
   summaries can be added later, and every step below works with empty `summary` fields.
2. **Directory file.** Publish the list as `directory.json` at the repo root, entries `{name, source, summary}`.
   Ship a copy in the plugin zip (add it to the `cp` line in `scripts/package.sh`) as the offline fallback.
3. **Fetch and cache.** The plugin downloads the newest `directory.json` from the repo over HTTPS (host must
   pass `github._allowed_host`; `raw.githubusercontent.com` does), caches it in the settings folder, and keeps
   the last good copy if a download is bad. Validate strictly: JSON object, size cap, `source` must be
   `curseforge:<digits>` or `owner/repo` (reuse `github.parse_repo`), strings length-capped. Never execute or
   trust anything else from it.
4. **Search the directory** in `search.py`: fuzzy-match name and summary, show the summary as the result's
   detail line. Keep the CurseForge-key results and merge them with `search.merge`.
5. **"Suggest an addon" button.** The plugin must not be able to write to the repo. It opens a prefilled GitHub
   issue in the browser (verify the Decky call, likely `Navigation.NavigateToExternalWeb` from `@decky/ui`;
   if it is unavailable show the URL in a `Message`). Maintainer merges suggestions by hand.
6. **CI check** (`.github/workflows`) for changes to `directory.json`: valid JSON, unique sources, source
   format, and that each CurseForge ID or GitHub repo exists. No bundle or release is produced by it.
7. Tests for 3 to 5, update the README, run tests, typecheck and rollup. Show the diff to the maintainer.

## Hard rules
- **Do not commit, tag, push or release unless the maintainer says "push"** (then follow `Ubermoc.md`).
  Local experiments may be committed with "(local, version unchanged)" only if he asks.
- **No secrets.** Never print, log or commit the Battle.net password, a CurseForge API key, or any token.
  The API key is the maintainer's; he will set `CF_API_KEY` himself. Do not ask him to paste it in chat.
- **Do not get around CurseForge's blocks.** Its search endpoints and project API return 403 without a
  key (Cloudflare). Do not spoof a browser User-Agent, replay the site's private API from a tab, or
  scrape in a way that bypasses a check. Reading ordinary pages in the maintainer's own browser at a
  polite pace (about 3 seconds apart, one tab) is fine; if a challenge appears, stop and report it.
- The maintainer-only tools (`tools/`, scraping, directory building) must never end up in the plugin zip or
  give users a way to change the directory. Publishing is controlled by who can merge to the repo.
- Don't expand scope: no extra features, no refactors of code you weren't asked to touch.
- Work in small verified steps. Say plainly what you ran and what you could not run (for example:
  the CurseForge key-based search was never tested live).

## 20. Addon directory and suggestion — built 2026-11-18, offline tested (not committed; the user pushes)

- `directory.json` at the repo root: 100 entries `{name, source, summary}`, from `tools/forever_top_ids.json` (top 100 forever addons). Built with `tools/make_directory.py` (his tooling, never in the zip — `scripts/package.sh` only copies the file). All 100 summaries filled: 48 from the original collection, 52 read 2026-11-18 through the relay in the maintainer's own Chrome (one tab, `summaries_todo.json` order, ~3 s apart, no challenge hit; `tools/summaries_done.json`, merged with `tools/merge_summaries.py`, file regenerated). Each summary is the page's top line under the name, copied exactly (the page line was confirmed equal to the `og:description` first line on sample pages).
- `py_modules/ubermoc_wow/directory.py`: `validate()` strict — JSON object, list ≤400, name ≤100, summary ≤200, source exactly `curseforge:<digits>` or `owner/repo` (`github.parse_repo`; `cf:` shorthand, prefixes, links rejected); extra keys dropped, never executed. `Directory.entries()`: fresh cache (`settings_dir/directory.json`, `{"cached": epoch, "addons": [...]}`) → fetch `https://raw.githubusercontent.com/ubermoc/Ubermoc-Warcraft-Mod-Updater/main/directory.json` (same `_allowed_host` + `_open` + `_read_limited` 200 KB cap as GitHub downloads; 15-minute cache window, attempt throttle) → last good cache → bundled `plugin_dir/directory.json`; never raises. `pnpm` can't run here, so `package.sh` itself was not executed (only its `cp` line verified).
- `search.py` `search_directory`: score = max(name, 0.7·summary), `MIN_SCORE` as before; `detail` = summary or source; `origin "directory"`. `service.search_addons` merges catalog + directory + CurseForge through `search.merge` (deduped by source).
- `service.suggest_issue(text)`: prefilled issue URL `https://github.com/ubermoc/Ubermoc-Warcraft-Mod-Updater/issues/new?title=Addon%20for%20the%20directory&body=Addon%3A%20…` (urlencode; ≥2 chars; `_allowed_host` re-check). No write path: the plugin only builds a link.
- UI: `src/api.ts` `suggestIssue` + origin `"directory"`; `src/RepoEditor.tsx` button "Suggest an addon for the directory" → `Navigation.NavigateToExternalWeb` (verified in `node_modules/@decky/ui/dist/modules/Router.d.ts`), fallback shows the URL in `Message`. Detail line shows `(directory)` for directory results.
- `tools/check_directory.py` (offline/online, exits 1 on bad format/duplicates/missing entries); CI `.github/workflows/directory.yml` runs it on `directory.json` changes only. Sample live check passed for `curseforge:3358` + `ubermoc/Ubermoc-UI` (`tools/sample_check.json`).
- Tests: 101 pass (`DirectoryStore` class: validation, size cap, cache, last-good copy, fallback, search, issue URL; `ServiceBase` stubs the fetch so existing tests stay offline). tsc and rollup pass.
- Not verified here: the live fetch of `directory.json` from `main` (404 until it is pushed), the browser in game, CI itself (runs on GitHub).

## Notes
- `main.py` returns `{ok, result}` or `{ok: false, error}` for every call; keep error text plain, telling
  the person what to do.
- Proton ignores filename case; match folders and WTF paths case-insensitively (see `installer._existing`).
- CurseForge's file lists (`/api/v1/mods/<id>/files`) work without a key and are how linked CurseForge
  addons update today. Flavor ids: mainline 517, classic 67408, bcc 73246, forever 88568.
