#!/usr/bin/env python3
"""Management CLI for WhisprFlow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


APP_DIR_NAME = "whisprflow-ubuntu"
CONFIG_DIR_NAME = "whisprflow"
LEGACY_CONFIG_DIR_NAME = "whisprtalk"
SERVICE_NAME = "whisprflow.service"
OPENWHISPR_ROOT = Path.home() / "openwhispr"
MODEL_DIR = Path.home() / ".cache" / "openwhispr" / "whisper-models"
MODEL_FILES = {
    "base": "ggml-base.bin",
    "large-v3-turbo": "ggml-large-v3-turbo.bin",
    "turbo": "ggml-large-v3-turbo.bin",
}
PROVIDERS = {"local_openwhispr", "openai"}
TRIGGERS = {"keyboard", "audio_button"}
PASTE_METHODS = {"auto", "xdotool", "wtype", "ydotool", "clipboard"}
BUTTON_STOP_MODES = {"silence", "release"}


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
    "custom_terms": [],
    "dictionary_files": ["~/.config/whisprflow/dictionary.txt"],
    "context_roots": [],
    "context_filenames": [".whisprflow-dictionary", "WHISPRFLOW.md", "AGENTS.md", "CLAUDE.md"],
    "prompt_max_chars": 900,
    "min_duration_sec": 0.3,
    "paste_method": "auto",
    "play_beeps": True,
    "release_tail_sec": 0.2,
    "keep_failed_wav": str(Path.home() / APP_DIR_NAME / "last_failed.wav"),
    "status_file": str(Path.home() / APP_DIR_NAME / "status.txt"),
    "hud_file": str(Path.home() / APP_DIR_NAME / "hud.txt"),
    "hud_preview_chars": 48,
}


def config_value_error(key: str, value: Any) -> str | None:
    if key not in DEFAULT_CONFIG:
        return f"unknown config key {key!r}"
    default = DEFAULT_CONFIG[key]
    if key == "provider" and value not in PROVIDERS:
        return f"provider must be one of {sorted(PROVIDERS)}"
    if key == "trigger" and value not in TRIGGERS:
        return f"trigger must be one of {sorted(TRIGGERS)}"
    if key == "paste_method" and value not in PASTE_METHODS:
        return f"paste_method must be one of {sorted(PASTE_METHODS)}"
    if key == "button_stop_mode" and value not in BUTTON_STOP_MODES:
        return f"button_stop_mode must be one of {sorted(BUTTON_STOP_MODES)}"
    if key in {"custom_terms", "dictionary_files", "context_roots", "context_filenames"}:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return None
        return f"{key} must be an array of strings"
    if default is None:
        if value is None or isinstance(value, str):
            return None
        return f"{key} must be null or string"
    if isinstance(default, bool):
        if isinstance(value, bool):
            return None
        return f"{key} must be boolean"
    if isinstance(default, int):
        if isinstance(value, int) and not isinstance(value, bool):
            return None
        return f"{key} must be integer"
    if isinstance(default, float):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return None
        return f"{key} must be number"
    if isinstance(default, str):
        if isinstance(value, str):
            return None
        return f"{key} must be string"
    return None


def validate_config(cfg: dict[str, Any]) -> list[str]:
    errors = []
    for key, value in cfg.items():
        error = config_value_error(key, value)
        if error:
            errors.append(error)
    return errors


def config_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = root / CONFIG_DIR_NAME / "config.json"
    legacy = root / LEGACY_CONFIG_DIR_NAME / "config.json"
    if not path.exists() and legacy.exists():
        return legacy
    return path


def load_config(merged: bool = False) -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return DEFAULT_CONFIG.copy() if merged else {}
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not merged:
        return loaded
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(loaded)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".config.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def parse_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def run_command(cmd: list[str], check: bool = False) -> int:
    try:
        return subprocess.run(cmd, check=check).returncode
    except FileNotFoundError:
        return 127


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def apply_button_audio_settings(cfg: dict[str, Any]) -> None:
    device = str(cfg.get("button_device") or "")
    alsa_card = env_first("WHISPRFLOW_ALSA_CARD", "WHISPRTALK_ALSA_CARD")
    mute_numid = env_first("WHISPRFLOW_ALSA_MUTE_NUMID", "WHISPRTALK_ALSA_MUTE_NUMID")
    mute_value = env_first("WHISPRFLOW_ALSA_MUTE_VALUE", "WHISPRTALK_ALSA_MUTE_VALUE", default="0,0")
    gain_numid = env_first("WHISPRFLOW_ALSA_GAIN_NUMID", "WHISPRTALK_ALSA_GAIN_NUMID")
    gain_value = env_first("WHISPRFLOW_ALSA_GAIN_VALUE", "WHISPRTALK_ALSA_GAIN_VALUE", default="63,63")
    button_port = env_first("WHISPRFLOW_BUTTON_PORT", "WHISPRTALK_BUTTON_PORT", default="analog-input-rear-mic")
    button_volume = env_first("WHISPRFLOW_BUTTON_VOLUME", "WHISPRTALK_BUTTON_VOLUME", default="46%")

    if alsa_card and mute_numid:
        run_command(["amixer", "-c", alsa_card, "cset", f"numid={mute_numid}", mute_value], check=False)
    if alsa_card and gain_numid:
        run_command(["amixer", "-c", alsa_card, "cset", f"numid={gain_numid}", gain_value], check=False)
    if device:
        run_command(["pactl", "set-source-port", device, button_port], check=False)
        run_command(["pactl", "set-source-volume", device, button_volume], check=False)


def openwhispr_server_path() -> Path:
    dist_path = OPENWHISPR_ROOT / "dist" / "linux-unpacked" / "resources" / "bin" / "whisper-server-linux-x64"
    if dist_path.exists():
        return dist_path
    return OPENWHISPR_ROOT / "resources" / "bin" / "whisper-server-linux-x64"


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def sorted_level_groups(samples: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    if not samples:
        return [], []
    ordered = sorted(samples, key=lambda item: (item[0], item[1]))
    group_size = max(1, len(ordered) // 3)
    return ordered[:group_size], ordered[-group_size:]


def level_stats(samples: list[tuple[int, int]]) -> dict[str, int]:
    if not samples:
        return {"avg": 0, "peak": 0}
    return {
        "avg": sum(avg for avg, _peak in samples) // len(samples),
        "peak": max(peak for _avg, peak in samples),
    }


def analyze_button_levels(samples: list[tuple[int, int]]) -> dict[str, Any]:
    idle_group, active_group = sorted_level_groups(samples)
    idle = level_stats(idle_group)
    active = level_stats(active_group)
    spread_avg = active["avg"] - idle["avg"]
    spread_peak = active["peak"] - idle["peak"]
    stats = {"idle": idle, "active": active, "samples": len(samples)}

    if len(samples) < 2 or (spread_avg < 500 and spread_peak < 1500):
        return {"verdict": "button not detected", "stats": stats, "recommendations": {}}
    if active["peak"] >= 32000:
        verdict = "button signal clipping"
    elif spread_avg < 1200 and spread_peak < 4000:
        verdict = "button too quiet"
    else:
        verdict = "good"

    threshold = max(200, idle["avg"] + max(300, int(spread_avg * 0.35)))
    peak_threshold = max(1000, idle["peak"] + max(1000, int(spread_peak * 0.35)))
    recommendations = {
        "button_threshold": int(threshold),
        "button_peak_threshold": int(peak_threshold),
        "button_peak_min_average": max(150, int(threshold * 0.65)),
        "button_press_chunks": 2,
        "button_rearm_threshold": max(100, int(idle["avg"] * 2.5)),
        "button_rearm_peak_threshold": max(500, int(idle["peak"] * 2.5)),
        "button_rearm_chunks": 10,
        "button_release_threshold": 0,
        "button_release_below_sec": 999,
    }
    return {"verdict": verdict, "stats": stats, "recommendations": recommendations}


def button_level_score(samples: list[tuple[int, int]]) -> int:
    idle_group, active_group = sorted_level_groups(samples)
    idle = level_stats(idle_group)
    active = level_stats(active_group)
    return max(0, active["avg"] - idle["avg"]) + max(0, active["peak"] - idle["peak"]) // 4


def rank_source_levels(source_samples: dict[str, list[tuple[int, int]]]) -> list[dict[str, Any]]:
    ranked = []
    for source, samples in source_samples.items():
        analysis = analyze_button_levels(samples)
        ranked.append(
            {
                "source": source,
                "score": button_level_score(samples),
                "verdict": analysis["verdict"],
                "stats": analysis["stats"],
                "recommendations": analysis["recommendations"],
            }
        )
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def analyze_mic_levels(samples: list[tuple[int, int]]) -> dict[str, Any]:
    silence_group, speech_group = sorted_level_groups(samples)
    silence = level_stats(silence_group)
    speech = level_stats(speech_group)
    spread_avg = speech["avg"] - silence["avg"]
    spread_peak = speech["peak"] - silence["peak"]
    stats = {"silence": silence, "speech": speech, "samples": len(samples)}

    if len(samples) < 2 or (spread_avg < 100 and speech["peak"] < 2500):
        return {"verdict": "speech not detected", "stats": stats, "recommendations": {}}
    if speech["peak"] >= 32000:
        verdict = "mic clipping"
    elif speech["avg"] < 180:
        verdict = "mic too quiet"
    else:
        verdict = "good"

    speech_threshold = max(120, silence["avg"] + max(120, int(spread_avg * 0.35)))
    peak_threshold = max(800, silence["peak"] + max(800, int(spread_peak * 0.35)))
    recommendations = {
        "mic_min_mean_abs": max(80, int(speech_threshold * 0.4)),
        "mic_speech_threshold": int(speech_threshold),
        "mic_speech_peak_threshold": int(peak_threshold),
        "mic_speech_peak_min_average": max(80, int(speech_threshold * 0.25)),
    }
    return {"verdict": verdict, "stats": stats, "recommendations": recommendations}


def audio_levels(data: bytes) -> tuple[int, int]:
    sample_count = len(data) // 2
    if sample_count <= 0:
        return 0, 0
    samples = struct.unpack(f"<{sample_count}h", data[: sample_count * 2])
    abs_samples = [abs(sample) for sample in samples]
    return sum(abs_samples) // sample_count, max(abs_samples)


def format_level_meter(label: str, sample: tuple[int, int]) -> str:
    avg, peak = sample
    return f"{label} avg={avg} peak={peak}"


def sample_parecord_levels(
    device: str,
    seconds: float,
    sample_rate: int,
    chunk_size: int = 1600,
    meter_label: str | None = None,
) -> list[tuple[int, int]]:
    if not device:
        raise ValueError("audio device is not configured")
    cmd = [
        "parecord",
        f"--device={device}",
        "--channels=1",
        f"--rate={int(sample_rate)}",
        "--raw",
        "--file-format=raw",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    samples: list[tuple[int, int]] = []
    deadline = time.monotonic() + float(seconds)
    try:
        assert proc.stdout is not None
        while time.monotonic() < deadline:
            data = proc.stdout.read(max(1, int(chunk_size)) * 2)
            if not data:
                break
            sample = audio_levels(data)
            samples.append(sample)
            if meter_label:
                print(format_level_meter(meter_label, sample), flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    if not samples and proc.stderr is not None:
        error = proc.stderr.read().decode("utf-8", errors="replace").strip()
        if error:
            print(f"parecord error: {error}", file=sys.stderr)
    return samples


def list_pulse_sources() -> list[str]:
    proc = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True, check=False)
    sources = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[1].endswith(".monitor"):
            sources.append(parts[1])
    return sources


def sample_many_parecord_levels(
    sources: list[str],
    seconds: float,
    sample_rate: int,
    chunk_size: int = 1600,
) -> dict[str, list[tuple[int, int]]]:
    results: dict[str, list[tuple[int, int]]] = {source: [] for source in sources}
    errors: dict[str, str] = {}

    def worker(source: str) -> None:
        try:
            results[source] = sample_parecord_levels(source, seconds, sample_rate, chunk_size)
        except Exception as exc:
            errors[source] = str(exc)

    threads = [threading.Thread(target=worker, args=(source,), daemon=True) for source in sources]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=float(seconds) + 5.0)
    for source, error in errors.items():
        print(f"{source}\terror\t{error}", file=sys.stderr)
    return results


def print_analysis(name: str, result: dict[str, Any]) -> None:
    print(f"{name} verdict: {result['verdict']}")
    print_json(result["stats"])
    if result["recommendations"]:
        print("recommended config:")
        print_json(result["recommendations"])


def countdown(label: str, seconds: float) -> None:
    whole_seconds = max(0, int(seconds))
    if whole_seconds <= 0:
        return
    for remaining in range(whole_seconds, 0, -1):
        print(f"{label} starts in {remaining}...", flush=True)
        time.sleep(1)


def cmd_config(args: argparse.Namespace) -> int:
    cfg = load_config(merged=args.action == "show")
    if args.action == "show":
        print(config_path())
        print_json(cfg)
        return 0
    if args.action == "get":
        value = load_config(merged=True).get(args.key)
        print_json(value)
        return 0
    if args.action == "set":
        cfg = load_config(merged=False)
        value = parse_value(args.value)
        error = config_value_error(args.key, value)
        if error:
            print(error, file=sys.stderr)
            return 2
        cfg[args.key] = value
        save_config(cfg)
        print(f"set {args.key}")
        return 0
    if args.action == "unset":
        cfg = load_config(merged=False)
        cfg.pop(args.key, None)
        save_config(cfg)
        print(f"unset {args.key}")
        return 0
    if args.action == "validate":
        errors = validate_config(load_config(merged=False))
        if errors:
            for error in errors:
                print(f"error\t{error}")
            return 1
        print(f"ok\t{config_path()}")
        return 0
    raise ValueError(f"unknown config action: {args.action}")


def cmd_service(args: argparse.Namespace) -> int:
    return run_command(["systemctl", "--user", args.action, SERVICE_NAME], check=False)


def cmd_logs(args: argparse.Namespace) -> int:
    cmd = ["journalctl", "--user", "-u", SERVICE_NAME]
    if args.follow:
        cmd.append("-f")
    else:
        cmd.extend(["-n", str(args.lines), "--no-pager"])
    return run_command(cmd, check=False)


def model_file(name: str) -> str:
    if name in MODEL_FILES:
        return MODEL_FILES[name]
    if name.startswith("ggml-") and name.endswith(".bin"):
        return name
    raise ValueError(f"unknown model {name!r}; expected one of {sorted(MODEL_FILES)}")


def download_model(name: str) -> int:
    file_name = model_file(name)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODEL_DIR / file_name
    if dest.exists():
        print(f"model exists: {dest}")
        return 0
    url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{file_name}"
    return run_command(["curl", "-L", "--fail", "--continue-at", "-", url, "-o", str(dest)], check=False)


def cmd_model(args: argparse.Namespace) -> int:
    if args.action == "list":
        cfg_model = os.environ.get("WHISPRFLOW_MODEL") or str(MODEL_DIR / MODEL_FILES["base"])
        for name, file_name in MODEL_FILES.items():
            if name == "turbo":
                continue
            path = MODEL_DIR / file_name
            status = "installed" if path.exists() else "missing"
            marker = " (default)" if str(path) == cfg_model else ""
            print(f"{name}\t{status}\t{path}{marker}")
        return 0
    if args.action == "install":
        return download_model(args.name)
    raise ValueError(f"unknown model action: {args.action}")


def cmd_openwhispr(args: argparse.Namespace) -> int:
    if args.action == "install":
        script = Path(__file__).resolve().parent / "install.sh"
        return run_command([str(script), "--no-apt", "--no-service"], check=False)
    if args.action == "pin":
        run_command(["git", "-C", str(OPENWHISPR_ROOT), "fetch", "--tags", "origin"])
        return run_command(["git", "-C", str(OPENWHISPR_ROOT), "checkout", args.ref])
    raise ValueError(f"unknown openwhispr action: {args.action}")


def cmd_devices(_args: argparse.Namespace) -> int:
    script = Path(__file__).resolve().parent / "scripts" / "list-audio-devices.sh"
    return run_command([str(script)], check=False)


def cmd_doctor(_args: argparse.Namespace) -> int:
    cfg = load_config(merged=True)
    checks = [
        ("python", shutil.which("python3") is not None),
        ("parecord", shutil.which("parecord") is not None),
        ("paste tool", any(shutil.which(name) for name in ("xdotool", "wtype", "ydotool", "wl-copy", "xclip", "xsel"))),
        ("openwhispr", openwhispr_server_path().exists()),
        ("model", Path(os.environ.get("WHISPRFLOW_MODEL") or MODEL_DIR / MODEL_FILES["base"]).exists()),
        ("config", config_path().exists()),
        ("button_device", bool(cfg.get("button_device"))),
        ("mic_device", bool(cfg.get("mic_device"))),
    ]
    failed = False
    for name, ok in checks:
        print(f"{'ok' if ok else 'warn'}\t{name}")
        failed = failed or not ok
    return 1 if failed else 0


def cmd_setup(args: argparse.Namespace) -> int:
    if getattr(args, "wizard", False):
        return cmd_wizard(args)
    script = Path(__file__).resolve().parent / "install.sh"
    cmd = [str(script)]
    if args.no_apt:
        cmd.append("--no-apt")
    if args.start:
        cmd.append("--start")
    return run_command(cmd, check=False)


def cmd_summary(_args: argparse.Namespace) -> int:
    cfg = load_config(merged=True)
    print("WhisprFlow summary")
    print(f"config\t{config_path()}")
    print(f"provider\t{cfg.get('provider')}")
    print(f"trigger\t{cfg.get('trigger')}")
    print(f"button_device\t{cfg.get('button_device') or '(unset)'}")
    print(f"mic_device\t{cfg.get('mic_device') or '(unset)'}")
    print(f"model\t{os.environ.get('WHISPRFLOW_MODEL') or MODEL_DIR / MODEL_FILES['base']}")
    print(f"paste_method\t{cfg.get('paste_method')}")
    print("next\twhisprflowctl test button")
    print("next\twhisprflowctl test mic")
    print("next\twhisprflowctl calibrate")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    cfg = load_config(merged=True)
    sample_rate = int(cfg.get("sample_rate", 16000))
    seconds = float(args.seconds)
    if args.target == "button":
        device = str(cfg.get("button_device") or "")
        apply_button_audio_settings(cfg)
        print(f"listening to button source: {device}")
        print(f"press and release the button for {seconds:g}s")
        samples = sample_parecord_levels(
            device,
            seconds,
            sample_rate,
            int(cfg.get("button_chunk_size", 1600)),
            "button" if getattr(args, "meter", False) else None,
        )
        result = analyze_button_levels(samples)
        print_analysis("button", result)
        return 0 if result["verdict"] == "good" else 1
    if args.target == "mic":
        device = str(cfg.get("mic_device") or "")
        print(f"listening to mic source: {device}")
        print(f"say: testing testing 123 for {seconds:g}s")
        samples = sample_parecord_levels(
            device,
            seconds,
            sample_rate,
            int(sample_rate * 0.1),
            "mic" if getattr(args, "meter", False) else None,
        )
        result = analyze_mic_levels(samples)
        print_analysis("mic", result)
        return 0 if result["verdict"] == "good" else 1
    if args.target == "sources":
        apply_button_audio_settings(cfg)
        sources = list_pulse_sources()
        if not sources:
            print("no PulseAudio/PipeWire input sources found", file=sys.stderr)
            return 1
        print("watching input sources:")
        for source in sources:
            marker = " (configured button)" if source == cfg.get("button_device") else ""
            print(f"- {source}{marker}")
        countdown("source test", float(getattr(args, "prep_seconds", 0)))
        print(f"click the button during the {seconds:g}s test window")
        samples = sample_many_parecord_levels(
            sources,
            seconds,
            sample_rate,
            int(cfg.get("button_chunk_size", 1600)),
        )
        ranked = rank_source_levels(samples)
        print("source ranking:")
        for item in ranked:
            stats = item["stats"]
            marker = " *configured*" if item["source"] == cfg.get("button_device") else ""
            print(
                f"{item['source']}{marker}\tscore={item['score']}\tverdict={item['verdict']}\t"
                f"idle_avg={stats['idle']['avg']}\tactive_avg={stats['active']['avg']}\t"
                f"active_peak={stats['active']['peak']}"
            )
        if ranked:
            best = ranked[0]
            configured = next((item for item in ranked if item["source"] == cfg.get("button_device")), None)
            print(f"best_source\t{best['source']}")
            if best["source"] != cfg.get("button_device") and best["verdict"] == "good":
                print(f"set_command\twhisprflowctl config set button_device {best['source']}")
            if best["verdict"] != "good":
                print("no source showed a clear button spike")
                if configured and configured["verdict"] == "button not detected":
                    print("diagnosis\tconfigured button source stayed flat")
                    if best["source"] != configured["source"] and best["score"] > configured["score"]:
                        print("diagnosis\tbest movement was on another mic, likely acoustic noise instead of the electrical button")
                    print("next\tcheck the button cable, jack, adapter wiring, and selected input port")
                return 1
            return 0
        return 1
    raise ValueError(f"unknown test target: {args.target}")


def cmd_calibrate(args: argparse.Namespace) -> int:
    cfg = load_config(merged=True)
    sample_rate = int(cfg.get("sample_rate", 16000))
    seconds = float(args.seconds)
    apply_button_audio_settings(cfg)
    print("button calibration")
    button_samples = sample_parecord_levels(
        str(cfg.get("button_device") or ""),
        seconds,
        sample_rate,
        int(cfg.get("button_chunk_size", 1600)),
    )
    button = analyze_button_levels(button_samples)
    print_analysis("button", button)
    print("mic calibration")
    mic_samples = sample_parecord_levels(
        str(cfg.get("mic_device") or ""),
        seconds,
        sample_rate,
        int(sample_rate * 0.1),
    )
    mic = analyze_mic_levels(mic_samples)
    print_analysis("mic", mic)

    recommendations = {}
    recommendations.update(button["recommendations"])
    recommendations.update(mic["recommendations"])
    if not recommendations:
        print("no config changes recommended")
        return 1
    if not args.apply:
        print("run with --apply to save these values")
        return 0
    saved = load_config(merged=False)
    saved.update(recommendations)
    save_config(saved)
    print(f"saved\t{config_path()}")
    return run_command(["systemctl", "--user", "restart", SERVICE_NAME], check=False)


def cmd_wizard(args: argparse.Namespace) -> int:
    print("WhisprFlow guided setup")
    doctor_code = cmd_doctor(args)
    print()
    cmd_summary(args)
    print()
    print("button test")
    prompt_enabled = not getattr(args, "no_prompt", False) and sys.stdin.isatty()
    if prompt_enabled:
        input("Press Enter, then click the button during the test window...")
    else:
        countdown("button test", float(getattr(args, "prep_seconds", 0)))
    button_code = cmd_test(argparse.Namespace(target="button", seconds=args.seconds, meter=True))
    print()
    print("mic test")
    if prompt_enabled:
        input("Press Enter, then say 'testing testing 123' during the test window...")
    else:
        countdown("mic test", float(getattr(args, "prep_seconds", 0)))
    mic_code = cmd_test(argparse.Namespace(target="mic", seconds=args.seconds, meter=True))
    if args.apply:
        print()
        return cmd_calibrate(argparse.Namespace(seconds=args.seconds, apply=True))
    return 1 if doctor_code or button_code or mic_code else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage WhisprFlow")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="run installer")
    setup.add_argument("--no-apt", action="store_true")
    setup.add_argument("--start", action="store_true")
    setup_sub = setup.add_subparsers(dest="setup_action")
    wizard = setup_sub.add_parser("wizard", help="run guided setup")
    wizard.add_argument("--seconds", type=float, default=6.0)
    wizard.add_argument("--prep-seconds", type=float, default=3.0)
    wizard.add_argument("--apply", action="store_true")
    wizard.add_argument("--no-prompt", action="store_true")
    wizard.set_defaults(wizard=True)
    setup.set_defaults(func=cmd_setup)

    sub.add_parser("doctor", help="check install health").set_defaults(func=cmd_doctor)
    sub.add_parser("devices", help="list audio devices").set_defaults(func=cmd_devices)
    sub.add_parser("summary", help="show current setup").set_defaults(func=cmd_summary)

    config = sub.add_parser("config", help="manage config")
    config_sub = config.add_subparsers(dest="action", required=True)
    config_sub.add_parser("show")
    config_sub.add_parser("validate")
    get = config_sub.add_parser("get")
    get.add_argument("key")
    set_cmd = config_sub.add_parser("set")
    set_cmd.add_argument("key")
    set_cmd.add_argument("value")
    unset = config_sub.add_parser("unset")
    unset.add_argument("key")
    config.set_defaults(func=cmd_config)

    service = sub.add_parser("service", help="manage user service")
    service_sub = service.add_subparsers(dest="action", required=True)
    for action in ("status", "start", "stop", "restart"):
        service_sub.add_parser(action)
    service.set_defaults(func=cmd_service)

    logs = sub.add_parser("logs", help="show service logs")
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("-n", "--lines", type=int, default=80)
    logs.set_defaults(func=cmd_logs)

    test = sub.add_parser("test", help="test audio button or mic")
    test_sub = test.add_subparsers(dest="target", required=True)
    for target in ("button", "mic", "sources"):
        target_parser = test_sub.add_parser(target)
        target_parser.add_argument("--seconds", type=float, default=6.0)
        target_parser.add_argument("--prep-seconds", type=float, default=0.0)
        target_parser.add_argument("--meter", action="store_true")
    test.set_defaults(func=cmd_test)

    calibrate = sub.add_parser("calibrate", help="measure and recommend audio thresholds")
    calibrate.add_argument("--seconds", type=float, default=6.0)
    calibrate.add_argument("--apply", action="store_true")
    calibrate.set_defaults(func=cmd_calibrate)

    model = sub.add_parser("model", help="manage STT models")
    model_sub = model.add_subparsers(dest="action", required=True)
    model_sub.add_parser("list")
    install = model_sub.add_parser("install")
    install.add_argument("name")
    model.set_defaults(func=cmd_model)

    openwhispr = sub.add_parser("openwhispr", help="manage OpenWhispr dependency")
    openwhispr_sub = openwhispr.add_subparsers(dest="action", required=True)
    openwhispr_sub.add_parser("install")
    pin = openwhispr_sub.add_parser("pin")
    pin.add_argument("ref")
    openwhispr.set_defaults(func=cmd_openwhispr)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
