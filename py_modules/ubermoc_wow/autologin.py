# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Type the saved password into a freshly started game's login screen, then press Enter.

The game remembers the account name and puts the cursor in its Password field itself.
Keys are sent through a virtual keyboard made with the kernel's uinput interface
(include/uapi/linux/uinput.h), so they reach the focused window in Gaming Mode and in
desktop mode. Typing is by key position on a US keyboard, so only printable ASCII works.

Safety: it only acts on a game it saw start after Play was pressed, never on one that
was already running (the password would land in chat), and it tries once.
"""

from __future__ import annotations

import fcntl
import logging
import os
import struct
import threading
import time
from pathlib import Path
from typing import Callable

from . import installer

log = logging.getLogger("ubermoc_wow.autologin")

START_TIMEOUT_S = 90.0   # waiting for the game to start
READY_TIMEOUT_S = 40.0   # waiting for the game's own startup log
SETTLE_S = 10.0          # after that, for the login screen to be ready for typing

_UI_SET_EVBIT, _UI_SET_KEYBIT, _UI_DEV_SETUP = 0x40045564, 0x40045565, 0x405C5503
_UI_DEV_CREATE, _UI_DEV_DESTROY = 0x5501, 0x5502
KEY_ENTER, KEY_LEFTSHIFT = 28, 42

# A US keyboard, row by row: the keys, and the codes they have in common.
_ROWS = (
    ("`1234567890-=", "~!@#$%^&*()_+", [41, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]),
    ("qwertyuiop[]\\", "QWERTYUIOP{}|", [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 43]),
    ("asdfghjkl;'", 'ASDFGHJKL:"', [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40]),
    ("zxcvbnm,./", "ZXCVBNM<>?", [44, 45, 46, 47, 48, 49, 50, 51, 52, 53]),
)
CHAR_MAP: dict[str, tuple[int, bool]] = {" ": (57, False)}
for _plain, _shifted, _codes in _ROWS:
    for _c, _s, _code in zip(_plain, _shifted, _codes):
        CHAR_MAP[_c] = (_code, False)
        CHAR_MAP[_s] = (_code, True)


def typable(text: str) -> bool:
    return all(c in CHAR_MAP for c in text)


class KeyboardError(Exception):
    pass


class VirtualKeyboard:
    def __init__(self) -> None:
        self._fd: int | None = None

    def open(self) -> None:
        if self._fd is not None:
            return
        try:
            fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
            fcntl.ioctl(fd, _UI_SET_EVBIT, 1)
            codes = {code for code, _ in CHAR_MAP.values()} | {KEY_ENTER, KEY_LEFTSHIFT}
            for code in codes:
                fcntl.ioctl(fd, _UI_SET_KEYBIT, code)
            fcntl.ioctl(fd, _UI_DEV_SETUP, struct.pack("HHHH80sI", 0x03, 0x1209, 0x7001, 1, b"Ubermoc WoW keyboard", 0))
            fcntl.ioctl(fd, _UI_DEV_CREATE)
        except OSError as e:
            raise KeyboardError(f"Couldn't make a virtual keyboard: {e}") from e
        self._fd = fd
        time.sleep(1.0)  # the system needs a moment to notice a new device

    def close(self) -> None:
        if self._fd is not None:
            try:
                fcntl.ioctl(self._fd, _UI_DEV_DESTROY)
            finally:
                os.close(self._fd)
                self._fd = None

    def _emit(self, kind: int, code: int, value: int) -> None:
        os.write(self._fd, struct.pack("llHHi", 0, 0, kind, code, value))

    def _tap(self, code: int, shift: bool) -> None:
        if shift:
            self._emit(1, KEY_LEFTSHIFT, 1)
            self._emit(0, 0, 0)
        self._emit(1, code, 1)
        self._emit(0, 0, 0)
        time.sleep(0.03)
        self._emit(1, code, 0)
        self._emit(0, 0, 0)
        if shift:
            self._emit(1, KEY_LEFTSHIFT, 0)
            self._emit(0, 0, 0)
        time.sleep(0.03)

    def type_text(self, text: str) -> None:
        self.open()
        try:
            for ch in text:
                code, shift = CHAR_MAP[ch]
                self._tap(code, shift)
        except OSError as e:
            raise KeyboardError(f"Typing failed: {e}") from e

    def press_enter(self) -> None:
        self.open()
        self._tap(KEY_ENTER, False)


def game_pids(folder: str) -> list[int]:
    """Processes running this game's own client, such as C:\\...\\_retail_\\Wow.exe."""
    wanted = folder.lower()
    found = []
    try:
        entries = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return found
    for pid in entries:
        args = installer._cmdline(pid)
        if args and args[0].lower().endswith("wow.exe") and wanted in args[0].lower().replace("\\", "/").split("/"):
            found.append(int(pid))
    return found


def startup_log_ready(game_path: str, since: float) -> bool:
    """The game rewrites Logs/gx.log on every start and logs 'Device Create Successful' once its graphics are up."""
    path = Path(game_path) / "Logs" / "gx.log"
    try:
        if path.stat().st_mtime < since:
            return False
        return "Device Create Successful" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


class AutoLogin:
    def __init__(
        self,
        read_password: Callable[[], str],
        keyboard: Callable[[], VirtualKeyboard] = VirtualKeyboard,
        pids: Callable[[str], list[int]] = game_pids,
        ready: Callable[[str, float], bool] = startup_log_ready,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ):
        self._read_password = read_password
        self._keyboard = keyboard
        self._pids = pids
        self._ready = ready
        self._sleep = sleep
        self._clock = clock
        self._states: dict[str, dict] = {}
        self._lock = threading.Lock()

    def state(self, game_id: str) -> dict:
        with self._lock:
            return dict(self._states.get(game_id, {"state": "idle", "message": ""}))

    def _set(self, game_id: str, state: str, message: str = "") -> None:
        with self._lock:
            self._states[game_id] = {"state": state, "message": message}

    def begin(self, game_id: str, folder: str, game_path: str) -> dict:
        """Call just before starting the game. Returns at once; typing happens in the background."""
        try:
            password = self._read_password()
        except Exception:  # noqa: BLE001  an unreadable login just means no auto login
            password = ""
        if not password:
            return {"started": False, "reason": "no password"}
        if self._pids(folder):
            self._set(game_id, "skipped", "The game is already running, so nothing was typed.")
            return {"started": False, "reason": "running"}
        with self._lock:
            if self._states.get(game_id, {}).get("state") in ("waiting", "typing"):
                return {"started": False, "reason": "busy"}
        self._set(game_id, "waiting", "Waiting for the login screen...")
        started_at = self._clock()
        thread = threading.Thread(target=self._run, args=(game_id, folder, game_path, started_at, password), daemon=True)
        thread.start()
        return {"started": True}

    def _run(self, game_id: str, folder: str, game_path: str, started_at: float, password: str) -> None:
        keyboard = None
        try:
            deadline = started_at + START_TIMEOUT_S
            while not self._pids(folder):
                if self._clock() > deadline:
                    self._set(game_id, "failed", "The game didn't start, so nothing was typed.")
                    return
                self._sleep(0.5)
            ready_by = self._clock() + READY_TIMEOUT_S
            while not self._ready(game_path, started_at) and self._clock() < ready_by:
                self._sleep(0.5)
            self._sleep(SETTLE_S)
            if not self._pids(folder):
                self._set(game_id, "failed", "The game closed before the login screen, so nothing was typed.")
                return
            self._set(game_id, "typing", "Logging in...")
            keyboard = self._keyboard()
            keyboard.type_text(password)
            self._sleep(0.3)
            keyboard.press_enter()
            self._set(game_id, "done", "Password sent. If it asks for an authenticator code, enter it yourself.")
        except KeyboardError as e:
            log.error("auto login failed: %s", e)
            self._set(game_id, "failed", str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("auto login failed")
            self._set(game_id, "failed", f"Something went wrong: {e.__class__.__name__}")
        finally:
            password = ""  # noqa: F841
            if keyboard is not None:
                try:
                    keyboard.close()
                except OSError:
                    pass
