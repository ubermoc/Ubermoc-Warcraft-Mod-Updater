// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { definePlugin, toaster } from "@decky/api";
import { ButtonItem, PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { FaDownload } from "react-icons/fa";

import { AddonItem, RowLabel } from "./AddonItem";
import {
  addAddon,
  AddonRow,
  AddonStatus,
  checkAddons,
  DefaultAddon,
  defaultAddons,
  dismissDefaultAddon,
  Game,
  listAddons,
  listGames,
} from "./api";
import { DefaultAddonPrompt } from "./DefaultAddonPrompt";
import { playGame } from "./play";
import { PluginUpdate } from "./PluginUpdate";
import { Message, RepoEditor } from "./RepoEditor";

const ADD_ROW = "\0add";

function shortVersion(version: string) {
  return version.split(".").slice(0, 3).join(".");
}

function PlayButton(props: { gameId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const play = async () => {
    setBusy(true);
    setError("");
    try {
      setError(await playGame(props.gameId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setTimeout(() => setBusy(false), 4000); // Steam takes a moment to start; don't launch twice
  };

  return (
    <>
      {error && <Message text={error} />}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={play}>
          {busy ? "Starting..." : "Play"}
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}

function Content() {
  const [games, setGames] = useState<Game[] | null>(null);
  const [gameError, setGameError] = useState("");
  // Only one game and one row inside it can be open at a time.
  const [openGame, setOpenGame] = useState<string | null>(null);
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [rows, setRows] = useState<AddonRow[]>([]);
  const [statuses, setStatuses] = useState<Record<string, AddonStatus>>({});
  const [listError, setListError] = useState("");
  const [suggested, setSuggested] = useState<DefaultAddon[]>([]);

  const scan = useCallback(async (rescan: boolean) => {
    const reply = await listGames(rescan);
    if (reply.ok) {
      setGames(reply.result);
      setGameError("");
    } else {
      setGames([]);
      setGameError(reply.error);
    }
  }, []);

  useEffect(() => {
    scan(false);
  }, [scan]);

  const loadGame = useCallback(async (gameId: string, fresh: boolean) => {
    const list = await listAddons(gameId);
    if (!list.ok) {
      setListError(list.error);
      return;
    }
    setListError("");
    setRows(list.result);
    try {
      const offer = await defaultAddons(gameId);
      setSuggested(offer.ok ? offer.result : []);
    } catch {
      setSuggested([]); // the offer is optional; never let it block the update check
    }
    const checked = await checkAddons(gameId, fresh);
    if (checked.ok) setStatuses(checked.result);
    else setListError(checked.error);
  }, []);

  const toggleGame = (id: string) => {
    setOpenRow(null);
    setRows([]);
    setStatuses({});
    setListError("");
    setSuggested([]);
    if (openGame === id) {
      setOpenGame(null);
    } else {
      setOpenGame(id);
      loadGame(id, false);
    }
  };

  const toggleRow = (key: string) => setOpenRow((current) => (current === key ? null : key));

  const add = (gameId: string) => async (text: string) => {
    const reply = await addAddon(gameId, text);
    if (reply.ok) {
      toaster.toast({ title: reply.result.title, body: `Installed ${reply.result.version}` });
      setOpenRow(null);
      await loadGame(gameId, false);
    }
    return reply;
  };

  const dismiss = async (gameId: string, folder: string) => {
    await dismissDefaultAddon(gameId, folder);
    setSuggested((current) => current.filter((addon) => addon.folder !== folder));
  };

  return (
    <>
      <PanelSection title="World of Warcraft">
        {games === null && <Message text="Looking for World of Warcraft..." />}
        {gameError && <Message text={gameError} />}
        {games?.length === 0 && !gameError && <Message text="No World of Warcraft install was found." />}
        {games?.map((game) => (
          <div key={game.id}>
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={() => toggleGame(game.id)}>
                <RowLabel title={game.label} detail={shortVersion(game.version)} open={openGame === game.id} />
              </ButtonItem>
            </PanelSectionRow>
            {openGame === game.id && (
              <>
                {listError && <Message text={listError} />}
                <PlayButton gameId={game.id} />
                {suggested.map((addon) => (
                  <DefaultAddonPrompt key={addon.folder} addon={addon} onInstall={add(game.id)} onDismiss={() => dismiss(game.id, addon.folder)} />
                ))}
                <PanelSectionRow>
                  <ButtonItem layout="below" onClick={() => toggleRow(ADD_ROW)}>
                    <RowLabel title="+ Add addon from GitHub" detail="" open={openRow === ADD_ROW} />
                  </ButtonItem>
                </PanelSectionRow>
                {openRow === ADD_ROW && (
                  <RepoEditor gameId={game.id} initial="" saveLabel="Install" onSave={add(game.id)} onCancel={() => setOpenRow(null)} />
                )}
                {rows.map((row) => (
                  <AddonItem
                    key={row.key}
                    gameId={game.id}
                    row={row}
                    status={statuses[row.key]}
                    open={openRow === row.key}
                    onToggle={() => toggleRow(row.key)}
                    onChanged={() => loadGame(game.id, false)}
                  />
                ))}
              </>
            )}
          </div>
        ))}
        {games?.length === 0 && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => scan(true)}>
              Rescan
            </ButtonItem>
          </PanelSectionRow>
        )}
      </PanelSection>
      <PluginUpdate />
    </>
  );
}

export default definePlugin(() => ({
  name: "Ubermoc Warcraft Mod Updater",
  titleView: <div className={staticClasses.Title}>Ubermoc Warcraft Mod Updater</div>,
  content: <Content />,
  icon: <FaDownload />,
}));
