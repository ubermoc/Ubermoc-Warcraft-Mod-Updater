# Ubermoc Warcraft Mod Updater

A [Decky Loader](https://decky.xyz/) plugin that finds World of Warcraft in your Steam Proton prefixes, lists each game by name (Midnight, Forever, Classic), and updates its addons from GitHub releases (and CurseForge) in Gaming Mode.

## Works together
Four projects made to be used together, so you can play World of Warcraft from the couch with only a controller:

- **[Ubermoc UI](https://github.com/ubermoc/Ubermoc-UI)** ([CurseForge](https://www.curseforge.com/wow/addons/ubermoc-ui)): the addon. It makes the game playable without a mouse or keyboard.
- **[Ubermoc Forever](https://github.com/ubermoc/Ubermoc-Forever)** ([CurseForge](https://www.curseforge.com/wow/addons/ubermoc-forever)): a default look for World of Warcraft: Forever that works 100% with a controller, made for the Steam Deck and Steam Controller and works with other controllers too.
- **[Ubermoc Speech](https://github.com/ubermoc/Ubermoc-Speech)**: a Decky plugin for typing. Hold a button, speak, and your words are typed into chat or anything else with focus.

Together: the Updater keeps the addons current, Ubermoc UI and Ubermoc Forever let you play, and Ubermoc Speech does the typing.

## Install

1. Download `Ubermoc-Warcraft-Mod-Updater.zip` from the [latest release](https://github.com/ubermoc/Ubermoc-Warcraft-Mod-Updater/releases/latest).
2. In Decky, open Settings, then Developer, and turn on Developer mode.
3. Choose Install Plugin from ZIP and pick the file.

## Use

- Login, at the top, saves your Battle.net password for both games. The game remembers your account name itself. With a password saved, Play types it and presses Enter once the login screen is ready. Where it can see the game's window (desktop mode) it types as soon as the window draws. In Game Mode the window can't be read, so it waits for the game's startup log and then a time scaled to how fast your device started the game. The Login wait slider scales that time: 1 is the safe default, lower is faster (0.4 worked on a fast desktop), and if your password is typed too early, raise it. It only does this for a game it started itself, never one that was already running, and it tries once. Each Play is a real login, so repeated rapid tests can make Blizzard ask for extra checks. Only letters, numbers and the symbols on a US keyboard can be typed. The password is encrypted with a key kept on the device (and tied to its TPM where there is one), or kept in a file only an administrator can read if the device can't encrypt. It's never shown again, and your authenticator code is never saved. What the login step did is written to the plugin's log.
- Play starts the game directly, without the Battle.net launcher. It makes a Steam shortcut called World of Warcraft Midnight (or Forever) that uses the same game files as your Battle.net install, with the Proton version that built that prefix (read from the prefix itself; if that can't be told it uses the one your Battle.net shortcut is set to). Battle.net is not needed once the game is installed. If something stops Play, it says in plain words what to do. What the login step did is written to the plugin's log.
- Open a game to see its addons. Only one game and one addon stay open at a time.
- An addon that isn't linked can be linked by opening it, entering where it comes from, and pressing Check. Save once the result looks right. Where it comes from can be:
  - `owner/repo` or a GitHub link: the repo's newest release.
  - `owner/repo@start`: the newest release whose tag starts with `start/`, for repos that publish several things in one releases list. Spoken is `rusty-key/spoken-wow@spoken`, its quest voices `rusty-key/spoken-wow@quests-audio`.
  - `curseforge:` and the Project ID from the addon's CurseForge page (for example `curseforge:1801478`): the newest release file for that game, read from curseforge.com.
- Some addons are known already and show as linked without doing anything: OpenXP, Spoken and its English voice packs, Forever Graphics Enhancer, Talents Forever, GearGuide, and the others in `catalog.json`. Folders that come from one download, such as Spoken and its modules, show as one row.
- At the bottom, under Plugin update, **Downloads: more Uber apps for game mode** opens a list of the other Uber apps (Uber Watch, Uber Watch for the desktop and Ubermoc Speech). Tapping one opens its GitHub page.
- Find by name, in Add addon and when linking an addon, looks up addons by name and fills in where it comes from. It is fuzzy, so typos and missing spaces still match. It always searches the addons this plugin already knows and the published addon directory (`directory.json` in this repo: the top 100 Forever addons with where each comes from and a one-sentence summary, so they can be added without typing anything; it grows as suggested addons are added, and "Suggest an addon for the directory" proposes one). A fresh copy is downloaded from GitHub at most every 15 minutes and cached in the settings folder; if a download is bad the last good copy is kept, and a copy shipped inside the plugin works offline. You can also keep a list of your own: a file called `directory.local.json` in the plugin's settings folder, in the same format (`{"addons": [{"name": "...", "source": "curseforge:123 or owner/repo", "summary": "..."}]}`). It stays on your device, is never published, and is searched together with the public one; a file with any invalid entry is ignored. Matching a name or its one-sentence summary shows the summary as the result's detail line. To search all of CurseForge, open CurseForge search at the top and save your own free API key from [console.curseforge.com](https://console.curseforge.com) (CurseForge doesn't allow searching without one). The key stays on the device and is never shown again. If an unlinked addon's own files name its CurseForge project, that is offered automatically.
- Suggest an addon, in the Find by name section, opens a prefilled GitHub issue on this repo with what you typed. The plugin can't write to the repo, so suggestions are merged by the maintainer by hand. If your Decky can't open a browser, the link is shown for copying.
- Add addon installs a new addon the same way.
- Edit changes a saved repo. Unlink forgets the link and leaves the addon installed.
- Clear saved data, under an open addon, deletes the settings it saved (its SavedVariables in the game's WTF folder, for every account and character) and keeps the addon installed. Delete removes the addon's folders from AddOns; an addon made of several parts (such as Spoken and its modules) can be deleted one part at a time, and a switch also clears its saved data. Both ask once more first, can't be undone, and need the game closed.
- The update button at the bottom updates the plugin in place and reloads it, the same way Ubermoc Speech does, so Decky and SteamOS don't need restarting.

## What it can update

An addon needs a GitHub release with a packaged `.zip`, ideally built with the [BigWigs packager](https://github.com/BigWigsMods/packager), or a release file on CurseForge. Repos with no releases, or with source code only, can't be installed. Downloads can be up to 3 GB, so large voice packs install too; they take a while.

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
