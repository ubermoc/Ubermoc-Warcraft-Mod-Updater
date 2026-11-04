# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""The saved Battle.net login: an email and, if the user chooses, a password.

The password is encrypted with systemd-creds, which keeps its key where only root can
read it and, when the machine has a TPM, ties it to that chip. Where that isn't
available the login is kept in a file only root can read, and the panel says so.
The password never goes back to the panel and never appears on a command line.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

CRED_NAME = "ubermoc-wow-login"
MAX_EMAIL = 320
MAX_PASSWORD = 256


class LoginError(Exception):
    """A problem to show to the user as it is."""


def _systemd_creds(args: list[str], data: bytes) -> bytes:
    exe = shutil.which("systemd-creds")
    if exe is None:
        raise OSError("systemd-creds isn't installed")
    done = subprocess.run([exe, *args], input=data, capture_output=True, timeout=15, check=True)
    return done.stdout


class LoginVault:
    def __init__(self, settings_dir: str | Path, run: Callable[[list[str], bytes], bytes] = _systemd_creds):
        self.path = Path(settings_dir) / "login.cred"
        self._run = run
        self._lock = threading.Lock()
        self._can_encrypt: bool | None = None

    # ---------- storage ----------
    def encrypts(self) -> bool:
        """Whether this device can encrypt the login. Asked once, then remembered."""
        if self._can_encrypt is None:
            try:
                sealed = self._run(["encrypt", f"--name={CRED_NAME}", "-", "-"], b"{}")
                self._can_encrypt = self._run(["decrypt", f"--name={CRED_NAME}", "-", "-"], sealed) == b"{}"
            except (OSError, subprocess.SubprocessError):
                self._can_encrypt = False
        return self._can_encrypt

    def _write(self, record: dict) -> None:
        blob = json.dumps(record).encode()
        if self.encrypts():
            try:
                sealed = self._run(["encrypt", f"--name={CRED_NAME}", "-", "-"], blob)
                body = {"v": 1, "method": "systemd-creds", "data": base64.b64encode(sealed).decode()}
            except (OSError, subprocess.SubprocessError):
                self._can_encrypt = False
                body = {"v": 1, "method": "file", **record}
        else:
            body = {"v": 1, "method": "file", **record}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def _read(self) -> dict | None:
        try:
            body = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise LoginError("The saved login couldn't be read. Remove it and save it again.")
        try:
            if body.get("method") == "systemd-creds":
                sealed = base64.b64decode(body["data"])
                record = json.loads(self._run(["decrypt", f"--name={CRED_NAME}", "-", "-"], sealed))
            else:
                record = {"email": body.get("email", ""), "password": body.get("password", "")}
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            raise LoginError("The saved login couldn't be decrypted on this device. Remove it and save it again.")
        return {"email": str(record.get("email", "")), "password": str(record.get("password", ""))}

    # ---------- what the panel sees ----------
    def status(self) -> dict:
        with self._lock:
            saved = self._read()
            return {
                "email": saved["email"] if saved else "",
                "has_password": bool(saved and saved["password"]),
                "encrypted": self.encrypts(),
            }

    def save(self, email: str, password: str) -> dict:
        email, password = email.strip(), password
        if not email:
            raise LoginError("Enter your email address.")
        if len(email) > MAX_EMAIL or len(password) > MAX_PASSWORD or any(c in email + password for c in "\r\n\0"):
            raise LoginError("That email or password isn't valid.")
        with self._lock:
            if not password:
                old = self._read()  # empty means keep the saved password; Remove clears it
                password = old["password"] if old else ""
            self._write({"email": email, "password": password})
        return self.status()

    def remove(self) -> dict:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        return self.status()

    def read(self) -> dict | None:
        """The saved login, for the backend only."""
        with self._lock:
            return self._read()
