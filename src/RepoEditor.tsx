// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { ButtonItem, Field, PanelSectionRow, TextField } from "@decky/ui";
import { useState } from "react";

import { checkRepo, FoundRelease, Reply } from "./api";

export function Message({ text }: { text: string }) {
  return (
    <PanelSectionRow>
      <Field focusable label={<div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{text}</div>} bottomSeparator="none" />
    </PanelSectionRow>
  );
}

// Type a repo, Check that it exists and fits this game, then confirm.
export function RepoEditor(props: {
  gameId: string;
  initial: string;
  saveLabel: string;
  onSave: (text: string) => Promise<Reply<unknown>>;
  onCancel: () => void;
}) {
  const [text, setText] = useState(props.initial);
  const [found, setFound] = useState<FoundRelease | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const check = async () => {
    setBusy(true);
    setError("");
    setFound(null);
    const reply = await checkRepo(props.gameId, text);
    if (reply.ok) setFound(reply.result);
    else setError(reply.error);
    setBusy(false);
  };

  const save = async () => {
    setBusy(true);
    setError("");
    const reply = await props.onSave(text);
    if (!reply.ok) {
      setError(reply.error);
      setBusy(false);
    }
    // On success the parent closes this editor.
  };

  return (
    <>
      <PanelSectionRow>
        <TextField
          label="GitHub repo"
          description="owner/repo or a GitHub link"
          value={text}
          disabled={busy}
          onChange={(e) => {
            setText(e.target.value);
            setFound(null);
            setError("");
          }}
        />
      </PanelSectionRow>
      {error && <Message text={error} />}
      {found && <Message text={`GitHub has: ${found.name} ${found.version}\nIs this the right addon?`} />}
      <PanelSectionRow>
        {found ? (
          <ButtonItem layout="below" disabled={busy} onClick={save}>
            {busy ? "Working..." : props.saveLabel}
          </ButtonItem>
        ) : (
          <ButtonItem layout="below" disabled={busy || text.trim() === ""} onClick={check}>
            {busy ? "Checking..." : "Check"}
          </ButtonItem>
        )}
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={props.onCancel}>
          Cancel
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
