# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""A test probe: watch Gamescope's video stream during a login and log numbers about it.

Why: in Game Mode the game's window can't be read through X (it reads black), so the plugin can't see
when the login screen is up. Gamescope does publish what it shows as a PipeWire video source, and
GStreamer's `pipewiresrc` can read it. This probe checks whether that works on the device and records,
over time, how bright the picture is and how much gold login-screen text is in the middle of it.

It only ever logs numbers. No picture is saved or kept, and it never touches the typing. Any failure
is logged and ignored. It runs only when the person picks the "Faster + screen test" Login timing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable

W, H = 640, 360
FRAME_BYTES = W * H * 3
FPS = 10
PROBE_MAX_S = 25.0
FIRST_FRAME_TIMEOUT_S = 8.0
# The middle of the screen, where the login panel is (fractions of the picture: left, top, right, bottom).
ZONE = (0.30, 0.38, 0.70, 0.72)
NON_BLACK_MEAN = 2.0


def analyse(frame: bytes) -> tuple[float, int, int]:
    """(average brightness 0-255, strict gold pixels, relaxed gold pixels) for one W x H RGB frame.
    "Gold" is the colour of the login screen's text; the relaxed test allows for scaling and blending."""
    mean = sum(frame) / len(frame)
    x0, y0, x1, y1 = int(ZONE[0] * W), int(ZONE[1] * H), int(ZONE[2] * W), int(ZONE[3] * H)
    strict = relaxed = 0
    for y in range(y0, y1):
        row = frame[(y * W + x0) * 3 : (y * W + x1) * 3]
        for r, g, b in zip(row[0::3], row[1::3], row[2::3]):
            if r > 150 and g > 120 and b < 110:
                relaxed += 1
                if r > 200 and g > 170 and b < 90:
                    strict += 1
    return mean, strict, relaxed


def video_sources(pw_dump_json: str) -> list[dict]:
    """The video sources PipeWire lists: [{"id", "name", "class"}]."""
    found = []
    for obj in json.loads(pw_dump_json):
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = (obj.get("info") or {}).get("props") or {}
        if str(props.get("media.class", "")).startswith("Video/Source"):
            found.append({"id": obj.get("id"), "name": str(props.get("node.name", "")), "class": props["media.class"]})
    return found


class ScreenProbe:
    def __init__(
        self,
        log,
        runtime_dir: str,
        clock: Callable[[], float] = time.time,
        run=subprocess.run,
        popen=subprocess.Popen,
        which=shutil.which,
    ):
        self._log = log
        self._runtime_dir = runtime_dir
        self._clock = clock
        self._run_cmd = run
        self._popen = popen
        self._which = which
        self._proc = None
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._guarded, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._kill()

    @staticmethod
    def _kill_proc(proc) -> None:
        try:
            proc.kill()
        except OSError:
            pass

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    def _env(self) -> dict:
        import os

        return {**os.environ, "XDG_RUNTIME_DIR": self._runtime_dir, "PIPEWIRE_RUNTIME_DIR": self._runtime_dir}

    def _guarded(self) -> None:
        try:
            self._probe()
        except Exception:  # noqa: BLE001  a probe must never affect the login
            self._log.exception("screen probe: failed")
        finally:
            self._kill()

    def _probe(self) -> None:
        began = self._clock()
        tools = {name: bool(self._which(name)) for name in ("pw-dump", "gst-launch-1.0", "gst-inspect-1.0")}
        self._log.info("screen probe: tools %s", tools)
        if not (tools["pw-dump"] and tools["gst-launch-1.0"]):
            self._log.info("screen probe: stopped, PipeWire or GStreamer tools are missing")
            return
        env = self._env()
        element = self._run_cmd(["gst-inspect-1.0", "pipewiresrc"], capture_output=True, env=env, timeout=10) if tools["gst-inspect-1.0"] else None
        if element is not None and element.returncode != 0:
            self._log.info("screen probe: stopped, GStreamer has no pipewiresrc")
            return
        dump = self._run_cmd(["pw-dump"], capture_output=True, text=True, env=env, timeout=10)
        if dump.returncode != 0:
            self._log.info("screen probe: stopped, pw-dump failed: %s", (dump.stderr or "")[:200].strip())
            return
        sources = video_sources(dump.stdout)
        self._log.info("screen probe: video sources %s", sources)
        chosen = next((s for s in sources if "gamescope" in s["name"].lower()), None)
        if chosen is None:
            self._log.info("screen probe: stopped, no Gamescope video source (this may not be Game Mode)")
            return
        # always-copy=true matters: without it the PipeWire source crashed after its first frame in testing.
        command = [
            "gst-launch-1.0", "pipewiresrc", f"path={chosen['id']}", "always-copy=true", "!",
            "videorate", "drop-only=true", "!", f"video/x-raw,framerate={FPS}/1", "!",
            "videoconvert", "!", "videoscale", "!", f"video/x-raw,format=RGB,width={W},height={H}", "!",
            "fdsink", "fd=1",
        ]
        # GStreamer's own messages go to a file (a pipe nobody reads would eventually block it) and are logged at the end.
        messages = tempfile.TemporaryFile()
        self._proc = self._popen(command, stdout=subprocess.PIPE, stderr=messages, env=env)
        proc = self._proc
        self._log.info("screen probe: watching '%s' (node %s), started %.1fs in", chosen["name"], chosen["id"], self._clock() - began)
        series = []
        first = {}
        start = self._clock()
        # A read from the stream blocks until a frame arrives, so timers end it by stopping GStreamer:
        # one if nothing shows up at all, and one for the overall time limit.
        for seconds, only_if_empty in ((FIRST_FRAME_TIMEOUT_S, True), (PROBE_MAX_S, False)):
            timer = threading.Timer(seconds, lambda e=only_if_empty: None if (e and series) else self._kill_proc(proc))
            timer.daemon = True
            timer.start()
        while not self._stop.is_set() and self._clock() - start < PROBE_MAX_S:
            data = proc.stdout.read(FRAME_BYTES)
            if len(data) < FRAME_BYTES:
                break
            now = self._clock() - start
            if series and now - series[-1][0] < 1.0 / FPS:
                continue  # the stream can run faster than we need; reading a frame is cheap, analysing it is not
            mean, strict, relaxed = analyse(data)
            series.append((now, mean, strict, relaxed))
            first.setdefault("frame", now)
            if mean > NON_BLACK_MEAN:
                first.setdefault("non_black", now)
            if strict >= 20:
                first.setdefault("gold_strict", now)
            if relaxed >= 20:
                first.setdefault("gold_relaxed", now)
        self._kill_proc(proc)
        try:
            messages.seek(0)
            said = messages.read(400).decode(errors="replace").replace("\n", " ").strip()
        except (OSError, ValueError):
            said = ""
        finally:
            messages.close()
        if said:
            self._log.info("screen probe: GStreamer said: %s", said)
        if not series:
            self._log.info("screen probe: no frames arrived")
            return
        self._log.info(
            "screen probe: %d frames. first frame %s, first not-black %s, gold (strict) %s, gold (relaxed) %s; seconds after the probe started",
            len(series), *(("%.1f" % first[k]) if k in first else "never" for k in ("frame", "non_black", "gold_strict", "gold_relaxed")),
        )
        step = max(1, FPS // 3)  # about 3 samples a second
        sampled = [f"{t:.1f}s:{m:.0f}/{s}/{r}" for t, m, s, r in series[::step]]
        for i in range(0, len(sampled), 20):
            self._log.info("screen probe: brightness/gold-strict/gold-relaxed %s", " ".join(sampled[i : i + 20]))
