# Ubermoc Warcraft Mod Updater

A [Decky Loader](https://decky.xyz/) plugin that finds World of Warcraft in your Steam Proton prefixes, lists each game by name (Midnight, Forever, Classic), and updates its addons from GitHub releases in Gaming Mode.

## Works together
Three projects made to be used together, so you can play World of Warcraft from the couch with only a controller:

- **[Ubermoc UI](https://github.com/ubermoc/Ubermoc-UI)** ([CurseForge](https://www.curseforge.com/wow/addons/ubermoc-ui)): the addon. It makes the game playable without a mouse or keyboard.
- **[Ubermoc Speech](https://github.com/ubermoc/Ubermoc-Speech)**: a Decky plugin for typing. Hold a button, speak, and your words are typed into chat or anything else with focus.

Together: the Updater keeps the addon current, Ubermoc UI lets you play, and Ubermoc Speech does the typing.

## Install

1. Download `Ubermoc-Warcraft-Mod-Updater.zip` from the [latest release](https://github.com/ubermoc/Ubermoc-Warcraft-Mod-Updater/releases/latest).
2. In Decky, open Settings, then Developer, and turn on Developer mode.
3. Choose Install Plugin from ZIP and pick the file.

## Use

- Login, at the top, saves your Battle.net password for both games. The game remembers your account name itself. The password is encrypted with a key kept on the device (and tied to its TPM where there is one), or kept in a file only an administrator can read if the device can't encrypt. It's never shown again, and your authenticator code is never saved. Saving a login does not sign you in by itself yet.
- Play starts the game directly, without the Battle.net launcher. It makes a Steam shortcut called World of Warcraft Midnight (or Forever) that uses the same Proton and game files as your Battle.net install. Battle.net is not needed once the game is installed.
- Open a game to see its addons. Only one game and one addon stay open at a time.
- An addon that isn't linked can be linked by opening it, entering `owner/repo` or a GitHub link, and pressing Check. Save once the result looks right.
- Midnight and Forever offer to install Ubermoc UI if it isn't installed. Not now is remembered for that game.
- Add addon from GitHub installs a new addon the same way.
- Edit changes a saved repo. Remove forgets the link and leaves the addon installed.
- The update button at the bottom updates the plugin in place and reloads it, the same way Ubermoc Speech does, so Decky and SteamOS don't need restarting.

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

## Support the project
Ubermoc Warcraft Mod Updater is free. If you'd like to say thanks, donations are optional and always appreciated:

- [GitHub Sponsors](https://github.com/sponsors/ubermoc)
- [Ko-fi](https://ko-fi.com/ubermoc)
- [Buy Me a Coffee](https://buymeacoffee.com/Ubermoc)

Made by Marcos ([Ubermoc](https://github.com/ubermoc)).
