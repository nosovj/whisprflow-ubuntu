#!/usr/bin/env python3
"""Push-to-talk Whisper dictation for Linux desktops."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import struct
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import requests
import sounddevice as sd
from pynput import keyboard


APP_DIR_NAME = "whisprflow-ubuntu"
CONFIG_DIR_NAME = "whisprflow"
LEGACY_CONFIG_DIR_NAME = "whisprtalk"

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "local_openwhispr",
    "trigger": "keyboard",
    "hotkey": "<f9>",
    "button_device": "",
    "button_threshold": 2600,
    "button_peak_threshold": 7800,
    "button_peak_min_average": 2200,
    "button_press_chunks": 2,
    "button_debug": False,
    "button_release_threshold": 2200,
    "button_release_below_sec": 0.5,
    "button_chunk_size": 1600,
    "button_latency_msec": 20,
    "button_debounce_sec": 1.5,
    "button_rearm_threshold": 700,
    "button_rearm_peak_threshold": 2000,
    "button_rearm_chunks": 10,
    "mic_device": "",
    "mic_channels": 2,
    "mic_channel": 0,
    "mic_preroll_enabled": False,
    "mic_preroll_sec": 0.8,
    "mic_speech_threshold": 600,
    "mic_speech_peak_threshold": 1500,
    "mic_speech_peak_min_average": 150,
    "mic_silence_stop_sec": 1.0,
    "mic_no_speech_stop_sec": 4.0,
    "mic_min_mean_abs": 220,
    "max_recording_sec": 15.0,
    "streaming_phrases": True,
    "phrase_preroll_sec": 0.4,
    "phrase_silence_sec": 0.7,
    "phrase_session_silence_stop_sec": 2.4,
    "phrase_min_duration_sec": 0.25,
    "mic_latency_msec": 20,
    "button_stop_mode": "silence",
    "sample_rate": 16000,
    "channels": 1,
    "model": "whisper-1",
    "local_url": "http://127.0.0.1:8180/inference",
    "language": None,
    "min_duration_sec": 0.3,
    "paste_method": "auto",
    "play_beeps": True,
    "release_tail_sec": 0.2,
    "keep_failed_wav": str(Path.home() / APP_DIR_NAME / "last_failed.wav"),
    "status_file": str(Path.home() / APP_DIR_NAME / "status.txt"),
    "hud_file": str(Path.home() / APP_DIR_NAME / "hud.txt"),
    "hud_preview_chars": 48,
}

PASTE_METHODS = {"auto", "xdotool", "wtype", "ydotool", "clipboard"}
PROVIDERS = {"openai", "local_openwhispr"}
TRIGGERS = {"keyboard", "audio_button"}
NOISE_TRANSCRIPTS = {
    "",
    "-",
    ".",
    "...",
    "[blank_audio]",
    "[ blank_audio ]",
    "[music]",
    "thank you.",
    "thanks for watching.",
    "yeah.",
    "okay.",
    "(clicks tongue)",
    "(clicking tongue)",
    "(click)",
}

BRACKETED_NOISE_RE = re.compile(r"\s*[\[(][^\])]{1,80}[\])]\s*")


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        config_root = Path(base)
    else:
        config_root = Path.home() / ".config"
    path = config_root / CONFIG_DIR_NAME / "config.json"
    legacy_path = config_root / LEGACY_CONFIG_DIR_NAME / "config.json"
    if not path.exists() and legacy_path.exists():
        return legacy_path
    return path


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
        return DEFAULT_CONFIG.copy()

    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    cfg = DEFAULT_CONFIG.copy()
    cfg.update(loaded)
    if cfg["provider"] not in PROVIDERS:
        raise ValueError(f"invalid provider {cfg['provider']!r}; expected one of {sorted(PROVIDERS)}")
    if cfg["trigger"] not in TRIGGERS:
        raise ValueError(f"invalid trigger {cfg['trigger']!r}; expected one of {sorted(TRIGGERS)}")
    if cfg["paste_method"] not in PASTE_METHODS:
        raise ValueError(
            f"invalid paste_method {cfg['paste_method']!r}; "
            f"expected one of {sorted(PASTE_METHODS)}"
        )
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def key_to_spec(key: keyboard.Key | keyboard.KeyCode) -> str:
    if isinstance(key, keyboard.Key):
        return f"<{key.name}>"
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            return key.char
        if key.vk is not None:
            return f"<{key.vk}>"
    raise ValueError(f"cannot format key {key!r}")


def key_vk(key: Any) -> int | None:
    vk = getattr(key, "vk", None)
    if vk is not None:
        return vk
    value = getattr(key, "value", None)
    return getattr(value, "vk", None)


def keys_match(expected: keyboard.Key | keyboard.KeyCode, actual: Any) -> bool:
    if actual == expected:
        return True
    expected_vk = key_vk(expected)
    actual_vk = key_vk(actual)
    return expected_vk is not None and actual_vk is not None and expected_vk == actual_vk


def parse_single_key(spec: str) -> keyboard.Key | keyboard.KeyCode:
    parsed = keyboard.HotKey.parse(spec)
    if len(parsed) != 1:
        raise ValueError(f"hotkey {spec!r} has {len(parsed)} keys; push-to-talk needs one key")
    return parsed[0]


def session_type() -> str:
    return (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()


def choose_paste_method(configured: str) -> str:
    if configured != "auto":
        return configured

    if session_type() == "wayland":
        for name in ("wtype", "ydotool"):
            if shutil.which(name):
                return name
        return "clipboard"

    if shutil.which("xdotool"):
        return "xdotool"
    return "clipboard"


def subprocess_timeout(text: str) -> float:
    return max(5.0, min(60.0, 0.02 * len(text) + 5.0))


def copy_to_clipboard(text: str) -> str:
    if shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=text, text=True, check=True, timeout=5)
        return "wl-copy"
    if shutil.which("xclip"):
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text,
            text=True,
            check=True,
            timeout=5,
        )
        return "xclip"
    if shutil.which("xsel"):
        subprocess.run(
            ["xsel", "--clipboard", "--input"],
            input=text,
            text=True,
            check=True,
            timeout=5,
        )
        return "xsel"
    raise RuntimeError("no clipboard tool found; install wl-clipboard, xclip, or xsel")


def paste_from_clipboard() -> bool:
    if session_type() == "wayland":
        if shutil.which("wtype"):
            subprocess.run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], check=True, timeout=5)
            return True
        if shutil.which("ydotool"):
            subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], check=True, timeout=5)
            return True
        return False

    if shutil.which("xdotool"):
        subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], check=True, timeout=5)
        return True
    return False


def paste_text(text: str, configured_method: str) -> str:
    method = choose_paste_method(configured_method)
    if method == "xdotool":
        if not shutil.which("xdotool"):
            raise RuntimeError("xdotool not found")
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", text],
            check=True,
            timeout=subprocess_timeout(text),
        )
        return "xdotool"

    if method == "wtype":
        if not shutil.which("wtype"):
            raise RuntimeError("wtype not found")
        subprocess.run(["wtype", "--", text], check=True, timeout=subprocess_timeout(text))
        return "wtype"

    if method == "ydotool":
        if not shutil.which("ydotool"):
            raise RuntimeError("ydotool not found")
        subprocess.run(["ydotool", "type", "--", text], check=True, timeout=subprocess_timeout(text))
        return "ydotool"

    if method == "clipboard":
        tool = copy_to_clipboard(text)
        if paste_from_clipboard():
            return f"clipboard ({tool})"
        return f"clipboard ({tool}; press Ctrl+V)"

    raise RuntimeError(f"unsupported paste method {method!r}")


def beep(freq_hz: float, enabled: bool) -> None:
    if not enabled:
        return
    try:
        rate = 44100
        duration = 0.08
        t = np.linspace(0, duration, int(rate * duration), False)
        tone = (0.12 * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
        sd.play(tone, rate, blocking=False)
    except Exception:
        pass


class Recorder:
    def __init__(self, sample_rate: int, channels: int) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            print(f"audio status: {status}", file=sys.stderr, flush=True)
        with self._lock:
            self._frames.append(indata.copy())

    def start(self) -> None:
        with self._lock:
            self._frames.clear()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> tuple[np.ndarray, float]:
        stream = self._stream
        self._stream = None
        if stream is not None:
            stream.stop()
            stream.close()

        with self._lock:
            frames = list(self._frames)
            self._frames.clear()

        if frames:
            audio = np.concatenate(frames, axis=0)
        else:
            audio = np.zeros((0, self.channels), dtype=np.int16)
        duration = len(audio) / float(self.sample_rate)
        return audio.astype(np.int16, copy=False), duration


class RingRecorder:
    def __init__(
        self,
        sample_rate: int,
        channels: int,
        preroll_sec: float = 0.8,
        speech_threshold: int = 120,
        silence_stop_sec: float = 1.0,
        no_speech_stop_sec: float | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.preroll_frames = max(0, int(float(preroll_sec) * self.sample_rate))
        self.speech_threshold = int(speech_threshold)
        self.silence_stop_sec = float(silence_stop_sec)
        self.no_speech_stop_sec = float(no_speech_stop_sec if no_speech_stop_sec is not None else silence_stop_sec)
        self.clock = clock
        self._lock = threading.Lock()
        self._ring: list[np.ndarray] = []
        self._ring_frames = 0
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._started_at = 0.0
        self._last_speech_at = 0.0
        self._heard_speech = False
        self._stream: sd.InputStream | None = None

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            print(f"audio status: {status}", file=sys.stderr, flush=True)
        self._accept_frame(indata.copy())

    def _accept_frame(self, frame: np.ndarray) -> None:
        frame = frame.astype(np.int16, copy=False)
        with self._lock:
            self._ring.append(frame.copy())
            self._ring_frames += len(frame)
            while self._ring and self._ring_frames - len(self._ring[0]) >= self.preroll_frames:
                removed = self._ring.pop(0)
                self._ring_frames -= len(removed)
            if self._recording:
                self._frames.append(frame.copy())
                if int(np.mean(np.abs(frame))) >= self.speech_threshold:
                    now = self.clock()
                    self._last_speech_at = now
                    self._heard_speech = True

    def open(self, device: str | None = None) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            device=device or None,
            callback=self._callback,
        )
        self._stream.start()

    def close(self) -> None:
        stream = self._stream
        self._stream = None
        if stream:
            stream.stop()
            stream.close()

    def start(self) -> None:
        with self._lock:
            self._frames = [frame.copy() for frame in self._ring]
            self._recording = True
            now = self.clock()
            self._started_at = now
            self._last_speech_at = now
            self._heard_speech = False

    def stop(self) -> tuple[np.ndarray, float]:
        with self._lock:
            frames = list(self._frames)
            self._frames.clear()
            self._recording = False
        if frames:
            audio = np.concatenate(frames, axis=0)
        else:
            audio = np.zeros((0, self.channels), dtype=np.int16)
        duration = len(audio) / float(self.sample_rate)
        return audio.astype(np.int16, copy=False), duration

    def should_auto_stop(self, min_duration_sec: float) -> bool:
        with self._lock:
            if not self._recording:
                return False
            now = self.clock()
            if now - self._started_at < float(min_duration_sec):
                return False
            if not self._heard_speech:
                return now - self._started_at >= self.no_speech_stop_sec
            return now - self._last_speech_at >= self.silence_stop_sec


class ParecordRingRecorder(RingRecorder):
    def __init__(
        self,
        sample_rate: int,
        channels: int,
        preroll_sec: float,
        device: str,
        speech_threshold: int = 120,
        silence_stop_sec: float = 1.0,
        no_speech_stop_sec: float | None = None,
    ) -> None:
        super().__init__(
            sample_rate,
            channels,
            preroll_sec,
            speech_threshold,
            silence_stop_sec,
            no_speech_stop_sec,
        )
        self.device = device
        self.process: subprocess.Popen[Any] | None = None
        self.thread: threading.Thread | None = None
        self._closed = threading.Event()

    def _accept_raw(self, data: bytes) -> None:
        sample_count = len(data) // 2
        if sample_count <= 0:
            return
        audio = np.frombuffer(data[: sample_count * 2], dtype=np.int16)
        if self.channels > 1:
            audio = audio.reshape(-1, self.channels)
        else:
            audio = audio.reshape(-1, 1)
        self._accept_frame(audio)

    def open(self, device: str | None = None) -> None:
        selected = device or self.device
        cmd = [
            "parecord",
            f"--device={selected}",
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            "--raw",
            "--file-format=raw",
        ]
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._closed.clear()
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _read_loop(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        chunk_bytes = max(3200, int(self.sample_rate * self.channels * 2 * 0.1))
        while not self._closed.is_set():
            data = self.process.stdout.read(chunk_bytes)
            if not data:
                break
            self._accept_raw(data)

    def close(self) -> None:
        self._closed.set()
        proc = self.process
        self.process = None
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)


class ParecordRecorder:
    def __init__(self, sample_rate: int, channels: int, device: str | None) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.device = device
        self.path: str | None = None
        self.process: subprocess.Popen[Any] | None = None
        self.started_at = 0.0

    def start(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        self.path = tmp.name
        cmd = [
            "parecord",
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            "--file-format=wav",
            self.path,
        ]
        if self.device:
            cmd.insert(1, f"--device={self.device}")
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.started_at = time.monotonic()

    def stop(self) -> tuple[str | None, float]:
        proc = self.process
        self.process = None
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        duration = time.monotonic() - self.started_at if self.started_at else 0.0
        return self.path, duration


class PhraseSegmenter:
    def __init__(
        self,
        sample_rate: int,
        channels: int,
        preroll_sec: float,
        speech_threshold: int,
        phrase_silence_sec: float,
        session_silence_stop_sec: float,
        no_speech_stop_sec: float,
        min_phrase_sec: float,
        speech_peak_threshold: int | None = None,
        speech_peak_min_average: int | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.preroll_frames = max(0, int(float(preroll_sec) * self.sample_rate))
        self.speech_threshold = int(speech_threshold)
        self.speech_peak_threshold = int(speech_peak_threshold if speech_peak_threshold is not None else 0)
        self.speech_peak_min_average = int(speech_peak_min_average if speech_peak_min_average is not None else 0)
        self.phrase_silence_sec = float(phrase_silence_sec)
        self.session_silence_stop_sec = float(session_silence_stop_sec)
        self.no_speech_stop_sec = float(no_speech_stop_sec)
        self.min_phrase_sec = float(min_phrase_sec)
        self.elapsed_sec = 0.0
        self._ring: list[np.ndarray] = []
        self._ring_frames = 0
        self._frames: list[np.ndarray] = []
        self._frame_count = 0
        self._in_phrase = False
        self._heard_speech = False
        self._last_speech_sec = 0.0

    def accept(self, frame: np.ndarray) -> list[np.ndarray]:
        frame = frame.astype(np.int16, copy=False)
        if frame.ndim == 1:
            frame = frame.reshape(-1, self.channels)
        duration = len(frame) / float(self.sample_rate)
        self.elapsed_sec += duration
        abs_frame = np.abs(frame)
        avg = int(np.mean(abs_frame)) if len(frame) else 0
        peak = int(np.max(abs_frame)) if len(frame) else 0
        speech = avg >= self.speech_threshold or (
            self.speech_peak_threshold > 0
            and peak >= self.speech_peak_threshold
            and avg >= self.speech_peak_min_average
        )
        finalized: list[np.ndarray] = []

        if speech:
            if not self._in_phrase:
                self._frames = [item.copy() for item in self._ring]
                self._frame_count = sum(len(item) for item in self._frames)
                self._in_phrase = True
            self._heard_speech = True
            self._last_speech_sec = self.elapsed_sec

        if self._in_phrase:
            self._frames.append(frame.copy())
            self._frame_count += len(frame)
            phrase_duration = self._frame_count / float(self.sample_rate)
            if (
                self._heard_speech
                and self.elapsed_sec - self._last_speech_sec >= self.phrase_silence_sec
                and phrase_duration >= self.min_phrase_sec
            ):
                finalized.append(np.concatenate(self._frames, axis=0).astype(np.int16, copy=False))
                self._frames = []
                self._frame_count = 0
                self._in_phrase = False
                self._ring = []
                self._ring_frames = 0
        else:
            self._ring.append(frame.copy())
            self._ring_frames += len(frame)
            while self._ring and self._ring_frames - len(self._ring[0]) >= self.preroll_frames:
                removed = self._ring.pop(0)
                self._ring_frames -= len(removed)

        return finalized

    def flush(self) -> np.ndarray | None:
        if not self._frames:
            return None
        phrase_duration = self._frame_count / float(self.sample_rate)
        if not self._heard_speech or phrase_duration < self.min_phrase_sec:
            self._frames = []
            self._frame_count = 0
            self._in_phrase = False
            return None
        audio = np.concatenate(self._frames, axis=0).astype(np.int16, copy=False)
        self._frames = []
        self._frame_count = 0
        self._in_phrase = False
        return audio

    def should_stop(self) -> bool:
        if not self._heard_speech:
            return self.elapsed_sec >= self.no_speech_stop_sec
        if self._in_phrase:
            return False
        return self.elapsed_sec - self._last_speech_sec >= self.session_silence_stop_sec


def write_wav(audio: np.ndarray, sample_rate: int, channels: int) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return tmp.name


def wav_with_selected_channel(path: str, channel: int | None) -> str:
    if channel is None:
        return path
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        if channels <= 1:
            return path
        if channel < 0 or channel >= channels:
            raise ValueError(f"mic_channel {channel} out of range for {channels} channels")
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if sample_width != 2:
        raise ValueError(f"unsupported wav sample width {sample_width}; expected 16-bit")
    audio = np.frombuffer(frames, dtype=np.int16).reshape(-1, channels)
    selected = audio[:, channel : channel + 1].astype(np.int16, copy=False)
    return write_wav(selected, sample_rate, 1)


def wav_mean_abs(path: str) -> int:
    with wave.open(path, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    if not frames:
        return 0
    audio = np.frombuffer(frames, dtype=np.int16)
    if len(audio) == 0:
        return 0
    return int(np.mean(np.abs(audio)))


def select_audio_channel(audio: np.ndarray, channel: int | None) -> np.ndarray:
    if audio.ndim != 2 or audio.shape[1] <= 1 or channel is None:
        return audio
    if channel < 0 or channel >= audio.shape[1]:
        raise ValueError(f"mic_channel {channel} out of range for {audio.shape[1]} channels")
    return audio[:, channel : channel + 1].astype(np.int16, copy=False)


def maybe_keep_failed_wav(path: str, cfg: dict[str, Any]) -> None:
    target = str(cfg.get("keep_failed_wav") or "")
    if not target:
        return
    dest = Path(target).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, dest)
    print(f"saved failed clip: {dest}", flush=True)


def set_status(cfg: dict[str, Any], text: str) -> None:
    target = str(cfg.get("status_file") or "")
    if not target:
        return
    path = Path(target).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.strip() + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"status update error: {exc}", file=sys.stderr, flush=True)


def hud_preview_text(text: str, max_chars: int = 48) -> str:
    normalized = normalize_transcript(text)
    if not normalized:
        return ""
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max(0, max_chars - 3)].rstrip() + "..."


def set_hud(cfg: dict[str, Any], text: str) -> None:
    target = str(cfg.get("hud_file") or "")
    if not target:
        return
    path = Path(target).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.strip() + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"hud update error: {exc}", file=sys.stderr, flush=True)


def average_amplitude(data: bytes) -> int:
    avg, _peak = audio_levels(data)
    return avg


def audio_levels(data: bytes) -> tuple[int, int]:
    if not data:
        return 0, 0
    sample_count = len(data) // 2
    if sample_count <= 0:
        return 0, 0
    samples = struct.unpack(f"<{sample_count}h", data[: sample_count * 2])
    abs_samples = [abs(sample) for sample in samples]
    return sum(abs_samples) // sample_count, max(abs_samples)


class AudioButtonDetector:
    def __init__(
        self,
        threshold: int,
        peak_threshold: int,
        peak_min_average: int,
        press_chunks: int,
        release_threshold: int,
        debounce_sec: float,
        release_below_sec: float,
        on_press: Any,
        on_release: Any,
        clock: Any = time.monotonic,
        rearm_threshold: int | None = None,
        rearm_peak_threshold: int | None = None,
        rearm_chunks: int = 1,
        start_armed: bool = True,
    ) -> None:
        self.threshold = int(threshold)
        self.peak_threshold = int(peak_threshold)
        self.peak_min_average = int(peak_min_average)
        self.press_chunks = max(1, int(press_chunks))
        self.release_threshold = int(release_threshold)
        self.debounce_sec = float(debounce_sec)
        self.release_below_sec = float(release_below_sec)
        self.rearm_threshold = int(rearm_threshold if rearm_threshold is not None else threshold)
        self.rearm_peak_threshold = int(rearm_peak_threshold if rearm_peak_threshold is not None else peak_threshold)
        self.rearm_chunks = max(1, int(rearm_chunks))
        self.on_press = on_press
        self.on_release = on_release
        self.clock = clock
        self.armed = bool(start_armed)
        self.pressed = False
        self.last_change = -float("inf")
        self.low_since: float | None = None
        self.high_chunks = 0
        self.idle_chunks = 0

    def require_rearm(self) -> None:
        self.armed = False
        self.pressed = False
        self.low_since = None
        self.high_chunks = 0
        self.idle_chunks = 0

    def process_amplitude(self, amplitude: int) -> None:
        self.process_levels(amplitude, 0)

    def process_levels(self, amplitude: int, peak: int) -> None:
        now = self.clock()
        idle = amplitude <= self.rearm_threshold and peak <= self.rearm_peak_threshold
        if idle:
            self.idle_chunks += 1
            if not self.armed and self.idle_chunks >= self.rearm_chunks:
                self.armed = True
        else:
            self.idle_chunks = 0

        if not self.armed:
            self.high_chunks = 0
            return

        if not self.pressed:
            high = amplitude >= self.threshold or (
                peak >= self.peak_threshold and amplitude >= self.peak_min_average
            )
            if not high:
                self.high_chunks = 0
                return
            self.high_chunks += 1
            if self.high_chunks < self.press_chunks:
                return
            if now - self.last_change <= self.debounce_sec:
                return
            started = self.on_press()
            if started:
                self.pressed = True
                self.armed = False
                self.low_since = None
                self.last_change = now
                self.high_chunks = 0
                self.idle_chunks = 0
            return

        if amplitude >= self.release_threshold:
            self.low_since = None
            return

        if self.low_since is None:
            self.low_since = now
            if self.release_below_sec > 0:
                return
        if now - self.low_since < self.release_below_sec:
            return
        if now - self.last_change <= self.debounce_sec:
            return
        self.on_release()
        self.pressed = False
        self.low_since = None
        self.high_chunks = 0
        self.last_change = now


def transcribe(path: str, cfg: dict[str, Any]) -> str:
    if cfg.get("provider") == "local_openwhispr":
        return transcribe_local_openwhispr(path, cfg)
    return transcribe_openai(path, cfg)


def transcribe_openai(path: str, cfg: dict[str, Any]) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing; export it or use ~/whisprflow-ubuntu/run.sh")

    data: dict[str, str] = {
        "model": str(cfg["model"]),
        "response_format": "text",
    }
    if cfg.get("language"):
        data["language"] = str(cfg["language"])

    with open(path, "rb") as f:
        files = {"file": ("audio.wav", f, "audio/wav")}
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
            timeout=120,
        )
    response.raise_for_status()
    return response.text.strip()


def normalize_transcript(text: str) -> str:
    return " ".join(text.replace("\n", " ").split()).strip()


def clean_transcript(text: str) -> str:
    return normalize_transcript(BRACKETED_NOISE_RE.sub("", text))


def parse_local_response(response_text: str, content_type: str = "") -> str:
    stripped = response_text.strip()
    if not stripped:
        return ""

    is_json = "json" in content_type.lower() or stripped[:1] in "[{"
    if is_json:
        result = json.loads(stripped)
        if isinstance(result, dict):
            if "error" in result:
                raise RuntimeError(str(result["error"]))
            if "text" in result:
                return normalize_transcript(str(result.get("text") or ""))
            transcription = result.get("transcription")
            if isinstance(transcription, list):
                return normalize_transcript("".join(str(seg.get("text", "")) for seg in transcription))
        if isinstance(result, str):
            return normalize_transcript(result)

    return normalize_transcript(stripped)


def is_noise_transcript(text: str) -> bool:
    normalized = normalize_transcript(text)
    lowered = normalized.lower()
    if lowered in NOISE_TRANSCRIPTS:
        return True
    if (
        ((normalized.startswith("(") and normalized.endswith(")")))
        or (normalized.startswith("[") and normalized.endswith("]"))
    ) and len(normalized) <= 80:
        return True
    if not clean_transcript(normalized):
        return True
    return False


def transcribe_local_openwhispr(path: str, cfg: dict[str, Any]) -> str:
    data: dict[str, str] = {"response_format": "json"}
    if cfg.get("language"):
        data["language"] = str(cfg["language"])

    with open(path, "rb") as f:
        files = {"file": ("audio.wav", f, "audio/wav")}
        response = requests.post(
            str(cfg["local_url"]),
            data=data,
            files=files,
            timeout=300,
        )
    response.raise_for_status()
    return parse_local_response(response.text, response.headers.get("content-type", ""))


class PhraseStreamingSession:
    def __init__(self, cfg: dict[str, Any], on_done: Any) -> None:
        self.cfg = cfg
        self.on_done = on_done
        self.sample_rate = int(cfg["sample_rate"])
        self.channels = int(cfg.get("mic_channels", cfg["channels"]))
        self.device = str(cfg.get("mic_device") or "")
        self.stop_event = threading.Event()
        self.queue: queue.Queue[tuple[int, str, float] | None] = queue.Queue()
        self.reader_thread: threading.Thread | None = None
        self.worker_thread: threading.Thread | None = None
        self.process: subprocess.Popen[Any] | None = None
        self.phrase_index = 0
        self.started_at = 0.0

    def start(self) -> None:
        self.started_at = time.monotonic()
        self.worker_thread = threading.Thread(target=self._commit_loop, daemon=True)
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.worker_thread.start()
        self.reader_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        proc = self.process
        if proc is not None:
            proc.terminate()

    def _read_loop(self) -> None:
        segmenter = PhraseSegmenter(
            self.sample_rate,
            self.channels,
            float(self.cfg.get("phrase_preroll_sec", 0.4)),
            int(self.cfg.get("mic_speech_threshold", 600)),
            float(self.cfg.get("phrase_silence_sec", 0.7)),
            float(self.cfg.get("phrase_session_silence_stop_sec", 2.4)),
            float(self.cfg.get("mic_no_speech_stop_sec", 4.0)),
            float(self.cfg.get("phrase_min_duration_sec", self.cfg.get("min_duration_sec", 0.3))),
            int(self.cfg.get("mic_speech_peak_threshold", 1500)),
            int(self.cfg.get("mic_speech_peak_min_average", 150)),
        )
        try:
            cmd = [
                "parecord",
                f"--rate={self.sample_rate}",
                f"--channels={self.channels}",
                f"--latency-msec={int(self.cfg.get('mic_latency_msec', 20))}",
                "--raw",
                "--file-format=raw",
            ]
            if self.device:
                cmd.insert(1, f"--device={self.device}")
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            assert self.process.stdout is not None
            chunk_bytes = max(1600, int(self.sample_rate * self.channels * 2 * 0.1))
            max_recording_sec = float(self.cfg.get("max_recording_sec", 15.0))
            while not self.stop_event.is_set():
                data = self.process.stdout.read(chunk_bytes)
                if not data:
                    break
                audio = self._raw_to_audio(data)
                for phrase in segmenter.accept(audio):
                    self._enqueue_phrase(phrase)
                if segmenter.should_stop():
                    break
                if time.monotonic() - self.started_at >= max_recording_sec:
                    print("max recording duration reached; stopping", flush=True)
                    break

            final_phrase = segmenter.flush()
            if final_phrase is not None:
                self._enqueue_phrase(final_phrase)
        except Exception as exc:
            print(f"phrase streaming error: {exc}", file=sys.stderr, flush=True)
            set_status(self.cfg, f"stream error: {exc}")
        finally:
            proc = self.process
            self.process = None
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            self.queue.put(None)
            if self.worker_thread is not None:
                self.worker_thread.join()
            self.on_done()

    def _raw_to_audio(self, data: bytes) -> np.ndarray:
        sample_count = len(data) // 2
        audio = np.frombuffer(data[: sample_count * 2], dtype=np.int16)
        if self.channels > 1:
            return audio.reshape(-1, self.channels)
        return audio.reshape(-1, 1)

    def _enqueue_phrase(self, audio: np.ndarray) -> None:
        audio = select_audio_channel(audio, self.cfg.get("mic_channel"))
        duration = len(audio) / float(self.sample_rate)
        if duration < float(self.cfg.get("phrase_min_duration_sec", self.cfg.get("min_duration_sec", 0.3))):
            return
        path = write_wav(audio, self.sample_rate, audio.shape[1])
        self.phrase_index += 1
        self.queue.put((self.phrase_index, path, duration))

    def _commit_loop(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                return
            index, path, duration = item
            self._commit_phrase(index, path, duration)

    def _commit_phrase(self, index: int, path: str, duration: float) -> None:
        try:
            mean_abs = wav_mean_abs(path)
            if mean_abs < int(self.cfg.get("mic_min_mean_abs", 220)):
                print(f"chunk {index}: mic too quiet; skipped paste (mean_abs={mean_abs})", flush=True)
                maybe_keep_failed_wav(path, self.cfg)
                set_status(self.cfg, f"skipped quiet chunk {index}")
                return
            set_status(self.cfg, f"transcribing chunk {index}")
            started = time.monotonic()
            text = transcribe(path, self.cfg)
            elapsed = time.monotonic() - started
            if not text:
                print(f"chunk {index}: empty transcript; skipped paste", flush=True)
                maybe_keep_failed_wav(path, self.cfg)
                set_status(self.cfg, f"skipped empty chunk {index}")
                return
            if is_noise_transcript(text):
                print(f"chunk {index}: noise transcript; skipped paste ({text!r})", flush=True)
                maybe_keep_failed_wav(path, self.cfg)
                set_status(self.cfg, f"skipped noise chunk {index}")
                return
            text = clean_transcript(text)
            if not text:
                print(f"chunk {index}: noise transcript; skipped paste", flush=True)
                maybe_keep_failed_wav(path, self.cfg)
                set_status(self.cfg, f"skipped noise chunk {index}")
                return

            preview = text.replace("\n", "\\n")
            if len(preview) > 100:
                preview = preview[:97] + "..."
            print(f"✎ chunk {index} {elapsed:.2f}s → {preview!r}", flush=True)
            method = paste_text(text, str(self.cfg["paste_method"]))
            print(f"pasted chunk {index} via {method}", flush=True)
            set_status(self.cfg, f"pasted chunk {index}")
            preview = hud_preview_text(text, int(self.cfg.get("hud_preview_chars", 48)))
            set_hud(self.cfg, preview)
            threading.Timer(2.0, set_hud, args=(self.cfg, "")).start()
        except Exception as exc:
            print(f"chunk {index}: commit error: {exc}", file=sys.stderr, flush=True)
            set_status(self.cfg, f"chunk {index} error")
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except Exception as exc:
                print(f"temp cleanup error: {exc}", file=sys.stderr, flush=True)


def capture_key() -> None:
    cfg = load_config()
    done = threading.Event()
    captured: dict[str, str] = {}

    def on_press(key: Any) -> bool:
        try:
            spec = key_to_spec(key)
            cfg["hotkey"] = spec
            save_config(cfg)
            captured["spec"] = spec
            print(f"captured {spec}", flush=True)
        except Exception as exc:
            print(f"capture failed: {exc}", file=sys.stderr, flush=True)
        finally:
            done.set()
        return False

    print("press macropad button once...", flush=True)
    with keyboard.Listener(on_press=on_press) as listener:
        while not done.wait(0.1):
            pass
        listener.stop()
    if not captured:
        raise SystemExit(1)


class WhisprFlow:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.expected_key = parse_single_key(str(cfg["hotkey"]))
        self.recorder = Recorder(int(cfg["sample_rate"]), int(cfg["channels"]))
        self.ring_recorder: RingRecorder | ParecordRingRecorder | None = None
        self.busy = threading.Lock()
        self.held = False
        self.held_lock = threading.Lock()
        self.recording = False
        self.active_clip = False
        self.reset_button_stream = False
        self.transient_ring_recorder = False
        self.recording_started_at = 0.0
        self.streaming_session: PhraseStreamingSession | None = None

    def on_press(self, key: Any) -> None:
        try:
            if not keys_match(self.expected_key, key):
                return
            with self.held_lock:
                if self.held:
                    return
                self.held = True

            if not self.busy.acquire(blocking=False):
                print("busy transcribing previous clip; skipped press", flush=True)
                return

            try:
                self.recorder.start()
                self.recording = True
                self.active_clip = True
                beep(880, bool(self.cfg.get("play_beeps", True)))
                print("● recording...", flush=True)
            except Exception:
                self.recording = False
                self.active_clip = False
                self.busy.release()
                raise
        except Exception as exc:
            print(f"press handler error: {exc}", file=sys.stderr, flush=True)

    def on_release(self, key: Any) -> None:
        release_busy = False
        tmp_path: str | None = None
        try:
            if not keys_match(self.expected_key, key):
                return
            with self.held_lock:
                self.held = False

            if not self.active_clip:
                return
            release_busy = True

            if not self.recording:
                return

            audio, duration = self.recorder.stop()
            self.recording = False
            beep(440, bool(self.cfg.get("play_beeps", True)))
            print(f"■ stopped ({duration:.2f}s)", flush=True)
            set_status(self.cfg, f"transcribing ({duration:.1f}s)")

            if duration < float(self.cfg["min_duration_sec"]):
                print(f"too short; skipped (< {self.cfg['min_duration_sec']}s)", flush=True)
                return

            audio = select_audio_channel(audio, self.cfg.get("mic_channel"))
            tmp_path = write_wav(audio, int(self.cfg["sample_rate"]), audio.shape[1])
            started = time.monotonic()
            text = transcribe(tmp_path, self.cfg)
            elapsed = time.monotonic() - started
            if not text:
                print("empty transcript; skipped paste", flush=True)
                maybe_keep_failed_wav(tmp_path, self.cfg)
                return
            if is_noise_transcript(text):
                print(f"noise transcript; skipped paste ({text!r})", flush=True)
                maybe_keep_failed_wav(tmp_path, self.cfg)
                return
            text = clean_transcript(text)
            if not text:
                print("noise transcript; skipped paste", flush=True)
                maybe_keep_failed_wav(tmp_path, self.cfg)
                return

            preview = text.replace("\n", "\\n")
            if len(preview) > 100:
                preview = preview[:97] + "..."
            print(f"✎ {elapsed:.2f}s → {preview!r}", flush=True)
            method = paste_text(text, str(self.cfg["paste_method"]))
            print(f"pasted via {method}", flush=True)
        except Exception as exc:
            print(f"release handler error: {exc}", file=sys.stderr, flush=True)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    print(f"temp cleanup error: {exc}", file=sys.stderr, flush=True)
            if release_busy:
                self.active_clip = False
                try:
                    self.busy.release()
                except RuntimeError:
                    pass

    def handle_audio_path(self, path: str | None, duration: float) -> None:
        tmp_path = path
        transcribe_path = path
        try:
            beep(440, bool(self.cfg.get("play_beeps", True)))
            print(f"■ stopped ({duration:.2f}s)", flush=True)

            if duration < float(self.cfg["min_duration_sec"]):
                print(f"too short; skipped (< {self.cfg['min_duration_sec']}s)", flush=True)
                set_status(self.cfg, "idle")
                return
            if not tmp_path:
                print("no audio path; skipped", flush=True)
                set_status(self.cfg, "idle")
                return

            transcribe_path = wav_with_selected_channel(tmp_path, self.cfg.get("mic_channel"))
            mean_abs = wav_mean_abs(transcribe_path)
            if mean_abs < int(self.cfg.get("mic_min_mean_abs", 220)):
                print(f"mic too quiet; skipped paste (mean_abs={mean_abs})", flush=True)
                maybe_keep_failed_wav(transcribe_path, self.cfg)
                set_status(self.cfg, f"skipped quiet ({mean_abs})")
                return
            started = time.monotonic()
            text = transcribe(transcribe_path, self.cfg)
            elapsed = time.monotonic() - started
            if not text:
                print("empty transcript; skipped paste", flush=True)
                maybe_keep_failed_wav(tmp_path, self.cfg)
                set_status(self.cfg, "skipped empty")
                return
            if is_noise_transcript(text):
                print(f"noise transcript; skipped paste ({text!r})", flush=True)
                maybe_keep_failed_wav(tmp_path, self.cfg)
                set_status(self.cfg, "skipped noise")
                return
            text = clean_transcript(text)
            if not text:
                print("noise transcript; skipped paste", flush=True)
                maybe_keep_failed_wav(tmp_path, self.cfg)
                set_status(self.cfg, "skipped noise")
                return

            preview = text.replace("\n", "\\n")
            if len(preview) > 100:
                preview = preview[:97] + "..."
            print(f"✎ {elapsed:.2f}s → {preview!r}", flush=True)
            method = paste_text(text, str(self.cfg["paste_method"]))
            print(f"pasted via {method}", flush=True)
            set_status(self.cfg, "pasted")
        except Exception as exc:
            print(f"audio-button release error: {exc}", file=sys.stderr, flush=True)
        finally:
            for cleanup_path in {tmp_path, transcribe_path}:
                if cleanup_path:
                    try:
                        os.unlink(cleanup_path)
                    except FileNotFoundError:
                        pass
                    except Exception as exc:
                        print(f"temp cleanup error: {exc}", file=sys.stderr, flush=True)
            self.active_clip = False
            self.recording = False
            self.reset_button_stream = True
            if self.cfg.get("status_file"):
                threading.Timer(2.0, set_status, args=(self.cfg, "idle")).start()
            try:
                self.busy.release()
            except RuntimeError:
                pass

    def on_audio_button_press(self) -> bool:
        try:
            if not self.busy.acquire(blocking=False):
                print("busy transcribing previous clip; skipped press", flush=True)
                return False
            if self.cfg.get("streaming_phrases"):
                self.recording = True
                self.active_clip = True
                self.recording_started_at = time.monotonic()
                self.streaming_session = PhraseStreamingSession(self.cfg, self.on_streaming_session_done)
                self.streaming_session.start()
                beep(880, bool(self.cfg.get("play_beeps", True)))
                print("● recording...", flush=True)
                set_status(self.cfg, "recording")
                set_hud(self.cfg, "")
                return True
            if self.ring_recorder is not None:
                self.ring_recorder.start()
                self.recorder = self.ring_recorder
            else:
                recorder = ParecordRingRecorder(
                    int(self.cfg["sample_rate"]),
                    int(self.cfg.get("mic_channels", self.cfg["channels"])),
                    0.0,
                    str(self.cfg.get("mic_device") or ""),
                    int(self.cfg.get("mic_speech_threshold", 600)),
                    float(self.cfg.get("mic_silence_stop_sec", 1.0)),
                    float(self.cfg.get("mic_no_speech_stop_sec", 4.0)),
                )
                self.recorder = recorder
                self.ring_recorder = recorder
                self.transient_ring_recorder = True
                recorder.open()
                recorder.start()
            self.recording = True
            self.active_clip = True
            self.recording_started_at = time.monotonic()
            beep(880, bool(self.cfg.get("play_beeps", True)))
            print("● recording...", flush=True)
            set_status(self.cfg, "recording")
            return True
        except Exception as exc:
            print(f"audio-button press error: {exc}", file=sys.stderr, flush=True)
            self.recording = False
            self.active_clip = False
            try:
                self.busy.release()
            except RuntimeError:
                pass
            return False

    def on_streaming_session_done(self) -> None:
        self.streaming_session = None
        self.active_clip = False
        self.recording = False
        self.recording_started_at = 0.0
        self.reset_button_stream = True
        if self.cfg.get("status_file"):
            threading.Timer(2.0, set_status, args=(self.cfg, "idle")).start()
        if self.cfg.get("hud_file"):
            threading.Timer(2.0, set_hud, args=(self.cfg, "")).start()
        try:
            self.busy.release()
        except RuntimeError:
            pass

    def on_audio_button_release(self) -> None:
        try:
            if self.streaming_session is not None:
                self.streaming_session.stop()
                return
            if not self.active_clip or not self.recording:
                return
            tail = float(self.cfg.get("release_tail_sec", 0.0))
            if tail > 0:
                time.sleep(tail)
            recorder = self.recorder
            if isinstance(recorder, RingRecorder):
                audio, duration = recorder.stop()
                audio = select_audio_channel(audio, self.cfg.get("mic_channel"))
                path = write_wav(audio, int(self.cfg["sample_rate"]), audio.shape[1])
                self.handle_audio_path(path, duration)
            elif isinstance(recorder, ParecordRecorder):
                path, duration = recorder.stop()
                self.handle_audio_path(path, duration)
            else:
                raise RuntimeError("audio-button trigger needs an audio recorder")
        except Exception as exc:
            print(f"audio-button release error: {exc}", file=sys.stderr, flush=True)
        finally:
            if self.transient_ring_recorder:
                transient = self.ring_recorder
                self.ring_recorder = None
                self.transient_ring_recorder = False
                if transient is not None:
                    transient.close()

    def run_audio_button(self) -> None:
        device = str(self.cfg["button_device"])
        chunk_size = int(self.cfg["button_chunk_size"])
        print(
            "ready. Hold audio button to dictate. "
            f"button={device} threshold={self.cfg['button_threshold']} "
            f"peak_threshold={self.cfg.get('button_peak_threshold', 9000)}",
            flush=True,
        )
        set_status(self.cfg, "idle")
        mic_device = str(self.cfg.get("mic_device") or "")
        if mic_device and self.cfg.get("mic_preroll_enabled"):
            self.ring_recorder = ParecordRingRecorder(
                int(self.cfg["sample_rate"]),
                int(self.cfg.get("mic_channels", self.cfg["channels"])),
                float(self.cfg.get("mic_preroll_sec", 0.8)),
                mic_device,
                int(self.cfg.get("mic_speech_threshold", 120)),
                float(self.cfg.get("mic_silence_stop_sec", 1.0)),
                float(self.cfg.get("mic_no_speech_stop_sec", 4.0)),
            )
        elif self.cfg.get("mic_preroll_enabled"):
            self.ring_recorder = RingRecorder(
                int(self.cfg["sample_rate"]),
                int(self.cfg.get("mic_channels", self.cfg["channels"])),
                float(self.cfg.get("mic_preroll_sec", 0.8)),
                int(self.cfg.get("mic_speech_threshold", 120)),
                float(self.cfg.get("mic_silence_stop_sec", 1.0)),
            )
        if self.ring_recorder is not None:
            try:
                self.ring_recorder.open()
            except Exception as exc:
                print(f"mic ring recorder failed; falling back to start-on-press: {exc}", file=sys.stderr, flush=True)
                self.ring_recorder = None
        proc = subprocess.Popen(
            [
                "parecord",
                f"--device={device}",
                "--channels=1",
                f"--rate={int(self.cfg['sample_rate'])}",
                f"--latency-msec={int(self.cfg.get('button_latency_msec', 20))}",
                "--raw",
                "--file-format=raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        def stop_process(_signum: int, _frame: Any) -> None:
            proc.terminate()
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, stop_process)
        detector = AudioButtonDetector(
            int(self.cfg["button_threshold"]),
            int(self.cfg.get("button_peak_threshold", 9000)),
            int(self.cfg.get("button_peak_min_average", 2200)),
            int(self.cfg.get("button_press_chunks", 2)),
            int(self.cfg.get("button_release_threshold", int(self.cfg["button_threshold"]) * 0.85)),
            float(self.cfg["button_debounce_sec"]),
            float(self.cfg.get("button_release_below_sec", 0.5)),
            self.on_audio_button_press,
            self.on_audio_button_release,
            rearm_threshold=int(self.cfg.get("button_rearm_threshold", int(self.cfg["button_threshold"]) * 0.85)),
            rearm_peak_threshold=int(self.cfg.get("button_rearm_peak_threshold", int(self.cfg.get("button_peak_threshold", 9000)))),
            rearm_chunks=int(self.cfg.get("button_rearm_chunks", 10)),
            start_armed=False,
        )
        try:
            while True:
                if self.reset_button_stream:
                    self.reset_button_stream = False
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                    proc = subprocess.Popen(
                        [
                            "parecord",
                            f"--device={device}",
                            "--channels=1",
                            f"--rate={int(self.cfg['sample_rate'])}",
                            f"--latency-msec={int(self.cfg.get('button_latency_msec', 20))}",
                            "--raw",
                            "--file-format=raw",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                    )
                    detector.require_rearm()
                    detector.last_change = time.monotonic()
                if proc.stdout is None:
                    break
                data = proc.stdout.read(chunk_size * 2)
                if not data:
                    break
                if (
                    self.active_clip
                    and self.cfg.get("button_stop_mode") == "silence"
                    and self.ring_recorder is not None
                    and self.ring_recorder.should_auto_stop(float(self.cfg["min_duration_sec"]))
                ):
                    self.on_audio_button_release()
                    continue
                if self.active_clip and self.recording_started_at:
                    if time.monotonic() - self.recording_started_at >= float(self.cfg.get("max_recording_sec", 15.0)):
                        print("max recording duration reached; stopping", flush=True)
                        self.on_audio_button_release()
                        continue
                avg, peak = audio_levels(data)
                if self.cfg.get("button_debug"):
                    print(f"button avg={avg} peak={peak}", flush=True)
                detector.process_levels(avg, peak)
        finally:
            proc.terminate()
            if self.ring_recorder is not None:
                self.ring_recorder.close()

    def run(self) -> None:
        if self.cfg.get("trigger") == "audio_button":
            self.run_audio_button()
            return
        print(
            f"ready. Hold {self.cfg['hotkey']} to dictate.",
            flush=True,
        )
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()


def print_config() -> None:
    cfg = load_config()
    print(config_path())
    print(json.dumps(cfg, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Push-to-talk Whisper dictation")
    parser.add_argument("--capture-key", action="store_true", help="capture next pressed key as hotkey")
    parser.add_argument("--config", action="store_true", help="print config path and contents")
    args = parser.parse_args()

    if args.config:
        print_config()
        return 0
    if args.capture_key:
        capture_key()
        return 0

    cfg = load_config()
    app = WhisprFlow(cfg)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
