# Ubermoc Warcraft Mod Updater

A [Decky Loader](https://decky.xyz/) plugin that finds World of Warcraft in your Steam Proton prefixes, lists each game by name (Midnight, Forever, Classic), and updates its addons from GitHub releases in Gaming Mode.

## Install

1. Download `Ubermoc-Warcraft-Mod-Updater.zip` from the [latest release](https://github.com/ubermoc/Ubermoc-Warcraft-Mod-Updater/releases/latest).
2. In Decky, open Settings, then Developer, and turn on Developer mode.
3. Choose Install Plugin from ZIP and pick the file.

## Use

- Open a game to see its addons. Only one game and one addon stay open at a time.
- An addon that isn't linked can be linked by opening it, entering `owner/repo` or a GitHub link, and pressing Check. Save once the result looks right.
- Add addon from GitHub installs a new addon the same way.
- Edit changes a saved repo. Remove forgets the link and leaves the addon installed.
- The update button at the bottom updates the plugin through Decky's own installer, so Decky and SteamOS don't need restarting.

## What it can update

An addon needs a GitHub release with a packaged `.zip`, ideally built with the [BigWigs packager](https://github.com/BigWigsMods/packager). Repos with no releases, or with source code only, can't be installed.

Only Steam and Proton installs are found. Lutris, Heroic and Bottles aren't scanned.

Close the game before updating its addons.

## Development

```bash
python3 -m unittest discover -s tests
```

```bash
bash scripts/package.sh
```

The package script needs pnpm 9. Pushing a `v*` tag that matches `package.json` publishes a release.
