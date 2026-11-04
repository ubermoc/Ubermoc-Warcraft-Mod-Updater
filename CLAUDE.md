# Ubermoc Warcraft Mod Updater work process

Decky Loader plugin (TypeScript frontend in `src/`, Python backend `main.py` + `py_modules/`) that finds WoW in Steam Proton prefixes, launches Midnight/Forever directly, and updates addons from GitHub releases in Gaming Mode. Repo github.com/ubermoc/Ubermoc-Warcraft-Mod-Updater.

## Every change
1. Make the change.
2. Run the tests: `python3 -m unittest discover -s tests -v`.
3. Build: `bash scripts/package.sh` (needs pnpm 9) -> `out/Ubermoc-Warcraft-Mod-Updater.zip`.
4. Local-only experiments may be committed with "(local, version unchanged)" in the message.

## "Push" = full release
Bump `version` in `package.json`, update README.md where behaviour changed, commit as `X.Y.Z: summary`, push `main`, then tag `vX.Y.Z` (must equal package.json's version or CI refuses) and push the tag. CI runs the tests, packages, and publishes a normal (non-prerelease) release, because the plugin's update button reads `/releases/latest`. Confirm with `gh run list` and `gh release list`.

## Care points
- The saved Battle.net password is encrypted on-device; never print, log or commit it, and never save authenticator codes.
- Play's auto-login only acts on a game the plugin started itself, once. Keep it that way.
