// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { toaster } from "@decky/api";
import { ButtonItem, DialogButton, PanelSectionRow, ToggleField } from "@decky/ui";
import { useState } from "react";
import { FaChevronDown, FaChevronRight } from "react-icons/fa";

import { AddonRow, AddonStatus, clearSavedData, removeAddon, removeLink, saveLink, updateAddon } from "./api";
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
  const [info, setInfo] = useState("");
  // Clearing and deleting can't be undone, so each asks once more first.
  const [confirm, setConfirm] = useState<"" | "clear" | "delete">("");
  const [alsoClear, setAlsoClear] = useState(false);

  const clearData = async () => {
    setBusy(true);
    setError("");
    setInfo("");
    const reply = await clearSavedData(gameId, row.key);
    if (reply.ok) setInfo(reply.result.message);
    else setError(reply.error);
    setConfirm("");
    setBusy(false);
  };

  const deleteAddon = async (folder: string) => {
    setBusy(true);
    setError("");
    setInfo("");
    const reply = await removeAddon(gameId, row.key, folder, alsoClear);
    if (reply.ok) {
      toaster.toast({ title: row.title, body: `Deleted ${reply.result.removed.join(", ")}` });
      setConfirm("");
      setAlsoClear(false);
      props.onToggle();
      await props.onChanged();
    } else {
      setError(reply.error);
    }
    setBusy(false);
  };

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
          initial={row.repo || row.suggestion}
          searchHint={row.title}
          note={!row.repo && row.suggestion ? "This addon's own files point to CurseForge. Press Check to use it, or find another source." : undefined}
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
                  Unlink
                </DialogButton>
              </div>
            </PanelSectionRow>
          )}
        </>
      )}
      {open && !editing && (
        <>
          {info && <Message text={info} />}
          {!row.repo && error && <Message text={error} />}
          {confirm === "" && (
            <>
              <PanelSectionRow>
                <ButtonItem layout="below" disabled={busy} onClick={() => setConfirm("clear")}>
                  Clear saved data
                </ButtonItem>
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" disabled={busy} onClick={() => setConfirm("delete")}>
                  Delete
                </ButtonItem>
              </PanelSectionRow>
            </>
          )}
          {confirm === "clear" && (
            <>
              <Message text={`Clear ${row.title}'s saved settings for every character? The addon stays installed and starts fresh. This can't be undone.`} />
              <PanelSectionRow>
                <ButtonItem layout="below" disabled={busy} onClick={clearData}>
                  {busy ? "Working..." : "Yes, clear it"}
                </ButtonItem>
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" disabled={busy} onClick={() => setConfirm("")}>
                  Cancel
                </ButtonItem>
              </PanelSectionRow>
            </>
          )}
          {confirm === "delete" && (
            <>
              <Message text={`Delete ${row.title} from this game? This can't be undone.`} />
              <PanelSectionRow>
                <ToggleField label="Also clear its saved data" checked={alsoClear} disabled={busy} onChange={setAlsoClear} />
              </PanelSectionRow>
              {row.folders.length > 1 &&
                row.folders.map((folder) => (
                  <PanelSectionRow key={folder}>
                    <ButtonItem layout="below" disabled={busy} onClick={() => deleteAddon(folder)}>
                      {`Delete only ${folder}`}
                    </ButtonItem>
                  </PanelSectionRow>
                ))}
              <PanelSectionRow>
                <ButtonItem layout="below" disabled={busy} onClick={() => deleteAddon("")}>
                  {busy ? "Working..." : row.folders.length > 1 ? `Delete all ${row.folders.length} parts` : "Yes, delete it"}
                </ButtonItem>
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" disabled={busy} onClick={() => setConfirm("")}>
                  Cancel
                </ButtonItem>
              </PanelSectionRow>
            </>
          )}
        </>
      )}
    </>
  );
}
