// Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import { ButtonItem, PanelSectionRow, SliderField, TextField, ToggleField } from "@decky/ui";
import { useEffect, useRef, useState } from "react";

import { loginSpeed, loginStatus, LoginStatus, removeLogin, Reply, saveLogin, screenTest, setLoginSpeed, setScreenTest } from "./api";
import { RowLabel } from "./AddonItem";
import { Message } from "./RepoEditor";

// The game remembers the account name itself. Only the password is saved here, and it never comes back.
export function LoginSection({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [status, setStatus] = useState<LoginStatus | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [probe, setProbe] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    loginSpeed().then((reply) => reply.ok && setSpeed(reply.result.speed), () => undefined);
    screenTest().then((reply) => reply.ok && setProbe(reply.result.on), () => undefined);
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
        <ButtonItem layout="below" onClick={onToggle}>
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
            <SliderField
              label="Login wait"
              description="How long Play waits for the login screen, as a multiple of how long your game took to start. 1 is the safe default and about 0.5 worked well in tests. Password typed too early? Raise it. Waiting too long? Lower it."
              value={speed}
              min={0}
              max={3}
              step={0.05}
              showValue
              editableValue
              valueSuffix="x"
              onChange={(value) => {
                setSpeed(value);
                if (saveTimer.current) clearTimeout(saveTimer.current);
                // Saved a moment after the slider stops moving, not on every step.
                saveTimer.current = setTimeout(async () => {
                  const reply = await setLoginSpeed(value);
                  if (!reply.ok) setError(reply.error);
                }, 500);
              }}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              label="Screen test"
              description="For testing. While Play logs in, also writes numbers about the game's picture to the plugin log. It saves no pictures and doesn't change when your password is typed."
              checked={probe}
              onChange={async (on) => {
                setProbe(on);
                const reply = await setScreenTest(on);
                if (!reply.ok) setError(reply.error);
              }}
            />
          </PanelSectionRow>
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
