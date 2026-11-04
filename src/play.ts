// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { PlayInfo, playInfo, saveShortcut, startLogin } from "./api";

// Steam's own client API. Its typings don't match every Steam build, so each call
// is checked on the live client first and a missing one ends in a clear error.
interface SteamApps {
  AddShortcut(name: string, exe: string, startDir: string, options: string): Promise<number>;
  SetShortcutName(appId: number, name: string): void;
  SetShortcutExe(appId: number, exe: string): void;
  SetShortcutStartDir(appId: number, dir: string): void;
  SetShortcutLaunchOptions(appId: number, options: string): void;
  SpecifyCompatTool(appId: number, tool: string): void;
}
interface SteamWindow {
  SteamClient?: { Apps?: SteamApps; URL?: { ExecuteSteamURL(url: string): void } };
  appStore?: { GetAppOverviewByAppID(appId: number): unknown };
  appDetailsStore?: { GetAppDetails(appId: number): { strCompatToolName?: string } | null };
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Steam keeps one Proton prefix per app, so a shortcut for Wow.exe would get an empty
// one. Pointing it at the prefix Battle.net installed the game into keeps the game's
// files, settings and Wine setup, and Battle.net itself never starts.
export async function playGame(gameId: string): Promise<string> {
  const win = window as unknown as SteamWindow;
  const apps = win.SteamClient?.Apps;
  if (!apps?.AddShortcut || !apps.SpecifyCompatTool || !win.SteamClient?.URL?.ExecuteSteamURL) {
    return "Steam can't set up Play on this version. Update Steam, then try again.";
  }
  const reply = await playInfo(gameId);
  if (!reply.ok) return reply.error;
  const info: PlayInfo = reply.result;

  // Use the Proton the Battle.net shortcut already runs, so the prefix is opened by the version that made it.
  const tool = win.appDetailsStore?.GetAppDetails(info.prefix_appid)?.strCompatToolName;
  if (!tool) return "Play needs to know your Proton version. In Steam, open your Battle.net game, go to Properties, then Compatibility, pick a Proton, and try Play again.";

  let appId = info.shortcut;
  if (!appId || !win.appStore?.GetAppOverviewByAppID(appId)) {
    appId = await apps.AddShortcut(info.name, info.exe, info.start_dir, "");
    if (!appId) return "Steam wouldn't add the Play shortcut. Restart Steam and try again.";
    await saveShortcut(gameId, appId);
    await wait(500); // Steam isn't ready for changes the instant it returns
  }
  apps.SetShortcutName(appId, info.name);
  // Quoted, like Steam's own shortcuts: the path has spaces and brackets and would otherwise break the launch command.
  apps.SetShortcutExe(appId, `"${info.exe}"`);
  apps.SetShortcutStartDir(appId, info.start_dir);
  apps.SetShortcutLaunchOptions(appId, `STEAM_COMPAT_DATA_PATH="${info.prefix}" %command%`);
  apps.SpecifyCompatTool(appId, tool);
  await wait(500);
  // Before the launch, so a game that was already running is never typed into.
  await startLogin(gameId);
  // Steam's own URL starts a shortcut in every Steam mode. Apps.RunGame did nothing on a live client.
  const steamGameId = (BigInt(appId) << 32n) | 0x02000000n;
  win.SteamClient.URL.ExecuteSteamURL(`steam://rungameid/${steamGameId}`);
  return "";
}
