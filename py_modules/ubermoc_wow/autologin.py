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
import re
import struct
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from . import installer

log = logging.getLogger("ubermoc_wow.autologin")

START_TIMEOUT_S = 90.0   # waiting for the game to start
READY_TIMEOUT_S = 45.0   # after it starts, the longest wait for either sign of a ready login screen
DRAWN_BRIGHTNESS = 2.0   # average 0-255 of the window; black reads ~0.2, the login screen ~77
POLL_S = 0.05
SETTLE_S = 10.0          # after the game's startup log appears, a fixed wait for the login screen
KEY_HOLD_S = 0.01        # how long each typed key is held down, and the gap after it
MOD_LEAD_S = 0.015       # Shift goes down this long before the key it changes
ENTER_HOLD_S = 0.06      # Enter is held longer: a key held only a few ms is missed by games that read input once per frame

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

    def _tap(self, code: int, shift: bool, hold: float = KEY_HOLD_S) -> None:
        if shift:
            self._emit(1, KEY_LEFTSHIFT, 1)
            self._emit(0, 0, 0)
            time.sleep(MOD_LEAD_S)  # let the game see Shift before the key it changes
        self._emit(1, code, 1)
        self._emit(0, 0, 0)
        time.sleep(hold)
        self._emit(1, code, 0)
        self._emit(0, 0, 0)
        if shift:
            self._emit(1, KEY_LEFTSHIFT, 0)
            self._emit(0, 0, 0)
        time.sleep(KEY_HOLD_S)

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
        self._tap(KEY_ENTER, False, ENTER_HOLD_S)


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


def _process_env(pid: int, names: tuple[str, ...]) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    found = {}
    for item in raw.split(b"\0"):
        key, _, value = item.partition(b"=")
        if key.decode(errors="replace") in names:
            found[key.decode()] = value.decode(errors="replace")
    return found


def _mean_of_ppm(data: bytes) -> float | None:
    """Average brightness (0-255) of a binary PPM, or None if it isn't one."""
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+(\d+)\s", data)
    if not m:
        return None
    pixels = data[m.end():]
    return sum(pixels) / len(pixels) if pixels else None


class ScreenCue:
    """Tells when the game window has drawn something, instead of still being black.

    It looks at a 5% sized copy of just the game's own window (ImageMagick's `import`, found
    with `xprop`), so it works at any resolution and only ever sees the game. Returns None when
    that isn't possible here (a tool is missing, no window yet), and the caller falls back to
    a timed wait. Nothing is saved to disk.
    """

    def __init__(self) -> None:
        self._window: str | None = None

    def _env(self, pid: int) -> dict[str, str] | None:
        """DISPLAY and XAUTHORITY for reaching the game's X server from outside its container.

        The game sees its own copy of XAUTHORITY inside Steam's container (/run/pressure-vessel/...),
        which doesn't exist out here, so Steam's own process supplies the real one.
        """
        env = _process_env(pid, ("DISPLAY", "XAUTHORITY"))
        if "DISPLAY" not in env:
            return None
        if not os.path.exists(env.get("XAUTHORITY", "")):
            env.pop("XAUTHORITY", None)
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    if Path(f"/proc/{entry}/comm").read_text().strip() != "steam":
                        continue
                except OSError:
                    continue
                theirs = _process_env(int(entry), ("XAUTHORITY",)).get("XAUTHORITY", "")
                if theirs and os.path.exists(theirs):
                    env["XAUTHORITY"] = theirs
                    break
        return {**os.environ, **env}

    def _find_window(self, pids: list[int], env: dict[str, str]) -> str | None:
        roots = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"], capture_output=True, text=True, env=env, timeout=3).stdout
        for wid in re.findall(r"0x[0-9a-f]+", roots):
            props = subprocess.run(["xprop", "-id", wid, "_NET_WM_PID"], capture_output=True, text=True, env=env, timeout=3).stdout
            m = re.search(r"=\s*(\d+)", props)
            if m and int(m.group(1)) in pids:
                return wid
        return None

    def __call__(self, pids: list[int]) -> bool | None:
        if not pids:
            return None
        try:
            env = self._env(pids[0])
            if env is None:
                return None
            if self._window is None:
                self._window = self._find_window(pids, env)
                if self._window is None:
                    return False  # the game is running but has no window yet
            shot = subprocess.run(["import", "-window", self._window, "-resize", "5%", "ppm:-"], capture_output=True, env=env, timeout=5)
            if shot.returncode != 0:
                self._window = None
                return None
            mean = _mean_of_ppm(shot.stdout)
            return None if mean is None else mean > DRAWN_BRIGHTNESS
        except (OSError, subprocess.SubprocessError):
            return None


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
        drawn: Callable[[list[int]], bool | None] | None = None,
        logger=None,
    ):
        self._drawn = drawn
        self._log = logger or log
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
            with self._lock:
                self._states.pop(game_id, None)  # never show a note left over from an earlier run
            return {"started": False, "reason": "no password"}
        if self._pids(folder):
            self._set(game_id, "skipped", "The game was already open, so your password wasn't typed. Close the game, then press Play.")
            return {"started": False, "reason": "running"}
        with self._lock:
            if self._states.get(game_id, {}).get("state") in ("waiting", "typing"):
                return {"started": False, "reason": "busy"}
        self._set(game_id, "waiting", "Waiting for the login screen...")
        started_at = self._clock()
        thread = threading.Thread(target=self._run, args=(game_id, folder, game_path, started_at, password), daemon=True)
        thread.start()
        return {"started": True}

    def _wait_until_ready(self, folder: str, game_path: str, started_at: float) -> str:
        """Wait for the login screen. Two signs are watched at once and the first one wins:
        the game's window has drawn something, or its startup log appeared SETTLE_S ago.
        (Where the window can't be read, such as under Gamescope, only the log counts.)
        Returns "window", "log", "closed" or "timeout"."""
        look = self._drawn or ScreenCue()
        began = self._clock()
        window_ok = True
        log_seen_at = None
        window_state = "black"
        while self._clock() - began < READY_TIMEOUT_S + SETTLE_S:
            pids = self._pids(folder)
            if not pids:
                return "closed"
            if window_ok:
                seen = look(pids)
                if seen is None:
                    window_ok, window_state = False, "unavailable"
                elif seen:
                    self._log.info("auto login: ready by window after %.1fs", self._clock() - began)
                    return "window"
            if log_seen_at is None and self._ready(game_path, started_at):
                log_seen_at = self._clock()
            if log_seen_at is not None and self._clock() - log_seen_at >= SETTLE_S:
                self._log.info(
                    "auto login: ready by startup log after %.1fs (window check: %s)", self._clock() - began, window_state
                )
                return "log"
            self._sleep(POLL_S if window_ok else 0.25)
        self._log.info("auto login: gave up after %.1fs (window check: %s)", self._clock() - began, window_state)
        return "timeout"

    def _run(self, game_id: str, folder: str, game_path: str, started_at: float, password: str) -> None:
        keyboard = None
        try:
            # Made first: the system needs about a second to notice a new keyboard.
            keyboard = self._keyboard()
            keyboard.open()
            deadline = started_at + START_TIMEOUT_S
            while not self._pids(folder):
                if self._clock() > deadline:
                    self._set(game_id, "failed", "The game didn't open. Press Play to try again.")
                    return
                self._sleep(0.2)
            self._log.info("auto login: game started %.1fs after Play", self._clock() - started_at)
            how = self._wait_until_ready(folder, game_path, started_at)
            if how == "closed":
                self._set(game_id, "failed", "The game closed too soon to log in. Press Play to try again.")
                return
            if how == "timeout":
                self._set(game_id, "failed", "Couldn't tell when the login screen was ready. Type your password in yourself.")
                return
            self._set(game_id, "typing", "Typing your password...")
            keyboard.type_text(password)
            self._sleep(0.15)
            keyboard.press_enter()
            self._log.info("auto login: password typed and Enter pressed")
            self._set(game_id, "done", "Password sent. If it asks for a code, type it in yourself.")
        except KeyboardError as e:
            self._log.error("auto login failed: %s", e)
            self._set(game_id, "failed", "Couldn't type your password on this device. Type it in yourself.")
        except Exception as e:  # noqa: BLE001
            self._log.exception("auto login failed")
            self._set(game_id, "failed", "Login didn't work. Type your password in yourself.")
        finally:
            password = ""  # noqa: F841
            if keyboard is not None:
                try:
                    keyboard.close()
                except OSError:
                    pass
