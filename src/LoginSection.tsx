// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { ButtonItem, PanelSectionRow, TextField } from "@decky/ui";
import { useEffect, useState } from "react";

import { loginStatus, LoginStatus, removeLogin, Reply, saveLogin } from "./api";
import { RowLabel } from "./AddonItem";
import { Message } from "./RepoEditor";

// The game remembers the account name itself. Only the password is saved here, and it never comes back.
export function LoginSection() {
  const [status, setStatus] = useState<LoginStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const apply = (reply: Reply<LoginStatus>) => {
    if (!reply.ok) {
      setError(reply.error);
      return;
    }
    setStatus(reply.result);
    setPassword("");
  };

  useEffect(() => {
    loginStatus().then(apply, () => setError("Couldn't read the saved password."));
  }, []);

  const work = async (job: () => Promise<Reply<LoginStatus>>) => {
    setBusy(true);
    setError("");
    try {
      apply(await job());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  const warning = status?.encrypted === false
    ? "Saved in a file only an administrator can read. It isn't encrypted, because this device can't encrypt it."
    : "Your password is encrypted with a key kept on this device. Anyone with admin access to this device can still recover it.";

  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => setOpen(!open)}>
          <RowLabel title="Login" detail={status?.has_password ? "Password saved" : "Not saved"} open={open} />
        </ButtonItem>
      </PanelSectionRow>
      {open && (
        <>
          <PanelSectionRow>
            <TextField
              label="Password"
              description={status?.has_password ? "Saved. Type a new one to replace it." : undefined}
              bIsPassword
              value={password}
              disabled={busy}
              onChange={(e) => setPassword(e.target.value)}
            />
          </PanelSectionRow>
          <Message text={`${warning}\nWith a saved password, Play types it in and presses Enter for you. Your authenticator code is never saved. Enter it with Steam's built-in keyboard, or say it with Ubermoc Speech.`} />
          {error && <Message text={error} />}
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || password === ""} onClick={() => work(() => saveLogin(password))}>
              {busy ? "Working..." : "Save"}
            </ButtonItem>
          </PanelSectionRow>
          {status?.has_password && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={busy} onClick={() => work(removeLogin)}>
                Remove saved password
              </ButtonItem>
            </PanelSectionRow>
          )}
        </>
      )}
    </>
  );
}
