// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useRef, useState } from "react";

import { checkPlugin, installPluginUpdate, PluginInfo, reloadAndShowPanel, restartDecky } from "./api";
import { Message } from "./RepoEditor";

// A working update reloads this panel. If it's still here after this long, the
// prompt was cancelled or the update failed, so offer the restart.
const RELOAD_WAIT_MS = 45000;

export function PluginUpdate() {
  const [info, setInfo] = useState<PluginInfo | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [offerRestart, setOfferRestart] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    checkPlugin().then((reply) => (reply.ok ? setInfo(reply.result) : setError(reply.error)));
    return () => clearTimeout(timer.current);
  }, []);

  const update = async () => {
    setBusy(true);
    setError("");
    try {
      const installed = await installPluginUpdate();
      if (!installed.ok) throw new Error(installed.error);
      await reloadAndShowPanel("Ubermoc Warcraft Mod Updater");
      timer.current = setTimeout(() => {
        setBusy(false);
        setOfferRestart(true);
      }, RELOAD_WAIT_MS);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
      setOfferRestart(true);
    }
  };

  const restart = async () => {
    try {
      await restartDecky();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <PanelSection title="Plugin update">
      <PanelSectionRow>
        <Field label="Current version" bottomSeparator="none">
          {info?.current ?? "..."}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Latest version" bottomSeparator="none">
          {info ? info.latest || "none yet" : "..."}
        </Field>
      </PanelSectionRow>
      {info?.message && <Message text={info.message} />}
      {error && <Message text={error} />}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || !info?.available} onClick={update}>
          {busy ? "Updating..." : info?.available ? "Update" : "Up to date"}
        </ButtonItem>
      </PanelSectionRow>
      {offerRestart && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={restart} description="Didn't update? This restarts Decky and Steam's interface.">
            Restart Decky Loader
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
