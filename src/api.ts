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

export interface PluginInfo {
  current: string;
  latest: string;
  available: boolean;
  message?: string;
}

export interface PreparedUpdate {
  path: string;
  name: string;
  version: string;
  hash: string;
}

export const listGames = callable<[rescan: boolean], Reply<Game[]>>("list_games");
export const listAddons = callable<[gameId: string], Reply<AddonRow[]>>("list_addons");
export const checkAddons = callable<[gameId: string, fresh: boolean], Reply<Record<string, AddonStatus>>>("check_addons");
export const checkRepo = callable<[gameId: string, text: string], Reply<FoundRelease>>("check_repo");
export const saveLink = callable<[gameId: string, key: string, text: string], Reply<FoundRelease>>("save_link");
export const removeLink = callable<[gameId: string, key: string], Reply<boolean>>("remove_link");
export const updateAddon = callable<[gameId: string, key: string], Reply<{ title: string; version: string }>>("update_addon");
export const addAddon = callable<[gameId: string, text: string], Reply<{ title: string; version: string }>>("add_addon");
export const checkPlugin = callable<[], Reply<PluginInfo>>("check_plugin");
export const prepareUpdate = callable<[], Reply<PreparedUpdate>>("prepare_plugin_update");

// Decky's own routes. Its UI uses them, but they aren't a documented plugin API,
// so a missing global must end in a clear error rather than a crash.
const UPDATE_INSTALL_TYPE = 2;

function deckyCall(route: string, ...args: unknown[]): Promise<unknown> {
  const backend = (window as unknown as { DeckyBackend?: { call: (route: string, ...args: unknown[]) => Promise<unknown> } })
    .DeckyBackend;
  if (!backend?.call) {
    throw new Error("This version of Decky doesn't offer the plugin installer.");
  }
  return backend.call(route, ...args);
}

export function installWithDecky(update: PreparedUpdate): Promise<unknown> {
  return deckyCall("utilities/install_plugin", `file://${update.path}`, update.name, update.version, update.hash, UPDATE_INSTALL_TYPE);
}

export function restartDecky(): Promise<unknown> {
  return deckyCall("updater/do_restart");
}
