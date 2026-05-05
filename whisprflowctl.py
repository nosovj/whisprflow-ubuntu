#!/usr/bin/env python3
"""Management CLI for WhisprFlow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
    return subprocess.run(cmd, check=check).returncode


def openwhispr_server_path() -> Path:
    dist_path = OPENWHISPR_ROOT / "dist" / "linux-unpacked" / "resources" / "bin" / "whisper-server-linux-x64"
    if dist_path.exists():
        return dist_path
    return OPENWHISPR_ROOT / "resources" / "bin" / "whisper-server-linux-x64"


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


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
        cfg[args.key] = parse_value(args.value)
        save_config(cfg)
        print(f"set {args.key}")
        return 0
    if args.action == "unset":
        cfg = load_config(merged=False)
        cfg.pop(args.key, None)
        save_config(cfg)
        print(f"unset {args.key}")
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
    script = Path(__file__).resolve().parent / "install.sh"
    cmd = [str(script)]
    if args.no_apt:
        cmd.append("--no-apt")
    if args.start:
        cmd.append("--start")
    return run_command(cmd, check=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage WhisprFlow")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="run installer")
    setup.add_argument("--no-apt", action="store_true")
    setup.add_argument("--start", action="store_true")
    setup.set_defaults(func=cmd_setup)

    sub.add_parser("doctor", help="check install health").set_defaults(func=cmd_doctor)
    sub.add_parser("devices", help="list audio devices").set_defaults(func=cmd_devices)

    config = sub.add_parser("config", help="manage config")
    config_sub = config.add_subparsers(dest="action", required=True)
    config_sub.add_parser("show")
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
