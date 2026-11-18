// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { ButtonItem, Field, Navigation, PanelSectionRow, TextField } from "@decky/ui";
import { useState } from "react";

import { checkRepo, FoundRelease, Reply, searchAddons, SearchResult, suggestIssue } from "./api";

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
  searchHint?: string; // the addon's name, to start the name search with
  note?: string;
  saveLabel: string;
  onSave: (text: string) => Promise<Reply<unknown>>;
  onCancel: () => void;
}) {
  const [text, setText] = useState(props.initial);
  const [found, setFound] = useState<FoundRelease | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [query, setQuery] = useState(props.searchHint ?? "");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searchNote, setSearchNote] = useState("");
  const [issueUrl, setIssueUrl] = useState("");

  // The plugin cannot write to the repo; a suggestion is a prefilled GitHub issue.
  const suggest = async () => {
    const reply = await suggestIssue(query.trim());
    if (!reply.ok) {
      setError(reply.error);
      return;
    }
    if (Navigation?.NavigateToExternalWeb) Navigation.NavigateToExternalWeb(reply.result.url);
    else setIssueUrl(reply.result.url); // older Decky: show the link so it can be opened by hand
  };

  const find = async () => {
    setBusy(true);
    setError("");
    setResults(null);
    const reply = await searchAddons(props.gameId, query);
    if (reply.ok) {
      setResults(reply.result.results);
      setSearchNote(reply.result.note);
    } else {
      setError(reply.error);
    }
    setBusy(false);
  };

  const pick = (result: SearchResult) => {
    setText(result.source);
    setResults(null);
    setFound(null);
    setError("");
  };

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
      {props.note && <Message text={props.note} />}
      <PanelSectionRow>
        <TextField
          label="Find by name"
          description="Fuzzy: typos and missing spaces are fine"
          value={query}
          disabled={busy}
          onChange={(e) => {
            setQuery(e.target.value);
            setResults(null);
          }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || query.trim().length < 2} onClick={find}>
          {busy ? "Searching..." : "Find"}
        </ButtonItem>
      </PanelSectionRow>
      {results && results.length === 0 && <Message text={`No match for "${query}".${searchNote ? `\n${searchNote}` : ""}`} />}
      {results && results.length > 0 && searchNote && <Message text={searchNote} />}
      {results?.map((r) => (
        <PanelSectionRow key={r.source}>
          <ButtonItem
            layout="below"
            description={`${r.detail}${r.origin === "curseforge" ? "  (CurseForge)" : r.origin === "directory" ? "  (directory)" : ""}`}
            onClick={() => pick(r)}
          >
            {r.title}
          </ButtonItem>
        </PanelSectionRow>
      ))}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || query.trim().length < 2} onClick={suggest}>
          Suggest an addon for the directory
        </ButtonItem>
      </PanelSectionRow>
      {issueUrl && <Message text={`Decky can't open a browser here.\n${issueUrl}`} />}
      <PanelSectionRow>
        <TextField
          label="Where it comes from"
          description="owner/repo, a GitHub link, owner/repo@tag-start, or curseforge: and the Project ID"
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
      {found && <Message text={`Found: ${found.name} ${found.version}\nIs this the right addon?`} />}
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
