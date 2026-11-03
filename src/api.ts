// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { callable } from "@decky/api";

export type Reply<T> = { ok: true; result: T } | { ok: false; error: string };

export interface Game {
  id: string;
  label: string;
  folder: string;
  version: string;
}

export interface AddonRow {
  key: string;
  title: string;
  folders: string[];
  version: string;
  repo: string;
  source: "link" | "toc" | "catalog" | "";
}

export interface AddonStatus {
  state: "current" | "update" | "unknown" | "unavailable" | "error";
  latest?: string;
  installed?: string;
  message?: string;
}

export interface FoundRelease {
  repo: string;
  name: string;
  version: string;
  filename: string;
}

export interface DefaultAddon {
  title: string;
  folder: string;
  repo: string;
  blurb: string;
}

export interface PluginInfo {
  current: string;
  latest: string;
  available: boolean;
  message?: string;
}

export const listGames = callable<[rescan: boolean], Reply<Game[]>>("list_games");
export const listAddons = callable<[gameId: string], Reply<AddonRow[]>>("list_addons");
export const checkAddons = callable<[gameId: string, fresh: boolean], Reply<Record<string, AddonStatus>>>("check_addons");
export const checkRepo = callable<[gameId: string, text: string], Reply<FoundRelease>>("check_repo");
export const saveLink = callable<[gameId: string, key: string, text: string], Reply<FoundRelease>>("save_link");
export const removeLink = callable<[gameId: string, key: string], Reply<boolean>>("remove_link");
export const updateAddon = callable<[gameId: string, key: string], Reply<{ title: string; version: string }>>("update_addon");
export const addAddon = callable<[gameId: string, text: string], Reply<{ title: string; version: string }>>("add_addon");
export const defaultAddons = callable<[gameId: string], Reply<DefaultAddon[]>>("default_addons");
export const dismissDefaultAddon = callable<[gameId: string, folder: string], Reply<boolean>>("dismiss_default_addon");
export const checkPlugin = callable<[], Reply<PluginInfo>>("check_plugin");
export const installPluginUpdate = callable<[], Reply<{ version: string }>>("install_plugin_update");

// Decky's own routes. Its UI uses them, but they aren't a documented plugin API,
// so a missing global must end in a clear error rather than a crash.
function deckyCall(route: string, ...args: unknown[]): Promise<unknown> {
  const backend = (window as unknown as { DeckyBackend?: { call: (route: string, ...args: unknown[]) => Promise<unknown> } })
    .DeckyBackend;
  if (!backend?.call) {
    throw new Error("This version of Decky doesn't offer the plugin installer.");
  }
  return backend.call(route, ...args);
}

// Decky keeps showing the old copy of an open panel after its plugin reloads, so
// once the new copy is loaded, open it. Returns false if Decky's state isn't there.
export async function reloadAndShowPanel(name: string): Promise<boolean> {
  type Plugin = { name: string };
  const state = (window as unknown as {
    DeckyPluginLoader?: { deckyState?: { publicState: () => { plugins: Plugin[] }; setActivePlugin: (name: string) => void } };
  }).DeckyPluginLoader?.deckyState;
  const find = () => state?.publicState().plugins.find((p) => p.name === name);
  const old = find();
  await deckyCall("loader/reload_plugin", name);
  if (!state) return false;
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const now = find();
    if (now && now !== old) {
      state.setActivePlugin(name);
      return true;
    }
  }
  return false;
}

export function restartDecky(): Promise<unknown> {
  return deckyCall("updater/do_restart");
}
