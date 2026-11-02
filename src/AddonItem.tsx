// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { toaster } from "@decky/api";
import { ButtonItem, DialogButton, PanelSectionRow } from "@decky/ui";
import { useState } from "react";
import { FaChevronDown, FaChevronRight } from "react-icons/fa";

import { AddonRow, AddonStatus, removeLink, saveLink, updateAddon } from "./api";
import { Message, RepoEditor } from "./RepoEditor";

function statusText(row: AddonRow, status?: AddonStatus): string {
  if (!row.repo) return "Not linked";
  if (!status) return "Checking...";
  switch (status.state) {
    case "current":
      return "Up to date";
    case "update":
      return "Update available";
    case "unknown":
      return "Version unknown";
    case "unavailable":
      return "No release";
    default:
      return "Check failed";
  }
}

export function RowLabel(props: { title: string; detail: string; open: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, width: "100%" }}>
      <span style={{ flex: 1, minWidth: 0, textAlign: "left", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {props.title}
      </span>
      <span style={{ fontSize: 12, opacity: 0.7, whiteSpace: "nowrap" }}>{props.detail}</span>
      {props.open ? <FaChevronDown size={11} /> : <FaChevronRight size={11} />}
    </div>
  );
}

export function AddonItem(props: {
  gameId: string;
  row: AddonRow;
  status?: AddonStatus;
  open: boolean;
  onToggle: () => void;
  onChanged: () => Promise<void>;
}) {
  const { gameId, row, status, open } = props;
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const update = async () => {
    setBusy(true);
    setError("");
    const reply = await updateAddon(gameId, row.key);
    if (reply.ok) {
      toaster.toast({ title: reply.result.title, body: `Updated to ${reply.result.version}` });
      await props.onChanged();
    } else {
      setError(reply.error);
    }
    setBusy(false);
  };

  const remove = async () => {
    setBusy(true);
    setError("");
    const reply = await removeLink(gameId, row.key);
    if (reply.ok) await props.onChanged();
    else setError(reply.error);
    setBusy(false);
  };

  const save = async (text: string) => {
    const reply = await saveLink(gameId, row.key, text);
    if (reply.ok) {
      setEditing(false);
      await props.onChanged();
    }
    return reply;
  };

  const canUpdate = status?.state === "update" || status?.state === "unknown";
  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={props.onToggle}>
          <RowLabel title={row.title} detail={statusText(row, status)} open={open} />
        </ButtonItem>
      </PanelSectionRow>
      {open && (editing || !row.repo) && (
        <RepoEditor
          gameId={gameId}
          initial={row.repo}
          saveLabel="Save"
          onSave={save}
          onCancel={() => {
            setEditing(false);
            if (!row.repo) props.onToggle();
          }}
        />
      )}
      {open && !editing && row.repo && (
        <>
          <Message
            text={
              status?.message ??
              `Installed ${status?.installed || row.version || "unknown"}\nLatest ${status?.latest || "unknown"}\n${row.repo}`
            }
          />
          {error && <Message text={error} />}
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || !canUpdate} onClick={update}>
              {busy ? "Working..." : canUpdate ? "Update" : "Up to date"}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={() => setEditing(true)}>
              Edit
            </ButtonItem>
          </PanelSectionRow>
          {row.source === "link" && (
            <PanelSectionRow>
              <div style={{ display: "flex", justifyContent: "center", padding: "2px 0 8px" }}>
                <DialogButton
                  disabled={busy}
                  onClick={remove}
                  style={{ width: "55%", minWidth: 0, minHeight: 0, height: 28, padding: "0 8px", fontSize: 12, lineHeight: "28px" }}
                >
                  Remove
                </DialogButton>
              </div>
            </PanelSectionRow>
          )}
        </>
      )}
    </>
  );
}
