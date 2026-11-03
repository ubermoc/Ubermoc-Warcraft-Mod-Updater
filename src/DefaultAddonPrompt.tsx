// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { useState } from "react";

import { DefaultAddon, Reply } from "./api";
import { Message } from "./RepoEditor";

export function DefaultAddonPrompt(props: {
  addon: DefaultAddon;
  onInstall: (repo: string) => Promise<Reply<unknown>>;
  onDismiss: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const install = async () => {
    setBusy(true);
    setError("");
    const reply = await props.onInstall(props.addon.repo);
    if (!reply.ok) {
      setError(reply.error);
      setBusy(false);
    }
    // On success the parent removes this prompt.
  };

  return (
    <>
      <Message text={`Install ${props.addon.title}?\n${props.addon.blurb}`} />
      {error && <Message text={error} />}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={install}>
          {busy ? "Installing..." : "Install"}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={props.onDismiss}>
          Not now
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
