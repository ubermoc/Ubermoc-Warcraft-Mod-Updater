// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { ButtonItem, PanelSectionRow, TextField } from "@decky/ui";
import { useEffect, useState } from "react";

import { RowLabel } from "./AddonItem";
import { curseforgeStatus, removeCurseforgeKey, Reply, saveCurseforgeKey } from "./api";
import { Message } from "./RepoEditor";

// CurseForge only lets apps search with a key. It's free, belongs to the person, and never comes back once saved.
export function CurseForgeKey() {
  const [open, setOpen] = useState(false);
  const [hasKey, setHasKey] = useState(false);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    curseforgeStatus().then((r) => r.ok && setHasKey(r.result.has_key), () => undefined);
  }, []);

  const work = async (job: () => Promise<Reply<{ has_key: boolean }>>) => {
    setBusy(true);
    setError("");
    try {
      const reply = await job();
      if (reply.ok) {
        setHasKey(reply.result.has_key);
        setKey("");
      } else {
        setError(reply.error);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => setOpen(!open)}>
          <RowLabel title="CurseForge search" detail={hasKey ? "Key saved" : "No key"} open={open} />
        </ButtonItem>
      </PanelSectionRow>
      {open && (
        <>
          <Message text="Finding addons by name on CurseForge needs your own free API key from console.curseforge.com. Without one, name search still finds the addons this plugin already knows. The key is kept on this device and never shown again." />
          <PanelSectionRow>
            <TextField
              label="API key"
              description={hasKey ? "Saved. Type a new one to replace it." : undefined}
              bIsPassword
              value={key}
              disabled={busy}
              onChange={(e) => setKey(e.target.value)}
            />
          </PanelSectionRow>
          {error && <Message text={error} />}
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || key.trim() === ""} onClick={() => work(() => saveCurseforgeKey(key))}>
              {busy ? "Working..." : "Save"}
            </ButtonItem>
          </PanelSectionRow>
          {hasKey && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={busy} onClick={() => work(removeCurseforgeKey)}>
                Remove saved key
              </ButtonItem>
            </PanelSectionRow>
          )}
        </>
      )}
    </>
  );
}
