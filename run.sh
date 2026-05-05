#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENWHISPR_ROOT="$HOME/openwhispr"
SERVER="${WHISPRFLOW_SERVER:-}"
if [[ -z "$SERVER" ]]; then
  if [[ -x "$OPENWHISPR_ROOT/dist/linux-unpacked/resources/bin/whisper-server-linux-x64" ]]; then
    SERVER="$OPENWHISPR_ROOT/dist/linux-unpacked/resources/bin/whisper-server-linux-x64"
  else
    SERVER="$OPENWHISPR_ROOT/resources/bin/whisper-server-linux-x64"
  fi
fi
MODEL="${WHISPRFLOW_MODEL:-${WHISPRTALK_MODEL:-$HOME/.cache/openwhispr/whisper-models/ggml-base.bin}}"
PORT="8180"
LOG="$ROOT/whisper-server.log"
PIDFILE="$ROOT/whisper-server.pid"
HUD_PIDFILE="$ROOT/hud.pid"
HUD_LOG="$ROOT/hud.log"

if [[ "${1:-}" != "--capture-key" && "${1:-}" != "--config" ]]; then
  CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}"
  CONFIG_FILE="$CONFIG_ROOT/whisprflow/config.json"
  if [[ ! -f "$CONFIG_FILE" && -f "$CONFIG_ROOT/whisprtalk/config.json" ]]; then
    CONFIG_FILE="$CONFIG_ROOT/whisprtalk/config.json"
  fi
  BUTTON_DEVICE="${WHISPRFLOW_BUTTON_DEVICE:-${WHISPRTALK_BUTTON_DEVICE:-}}"
  if [[ -z "$BUTTON_DEVICE" && -f "$CONFIG_FILE" ]]; then
    BUTTON_DEVICE="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("button_device") or "")' "$CONFIG_FILE")"
  fi

  # Optional local tuning for audio-jack button sources.
  ALSA_CARD="${WHISPRFLOW_ALSA_CARD:-${WHISPRTALK_ALSA_CARD:-}}"
  ALSA_MUTE_NUMID="${WHISPRFLOW_ALSA_MUTE_NUMID:-${WHISPRTALK_ALSA_MUTE_NUMID:-}}"
  ALSA_MUTE_VALUE="${WHISPRFLOW_ALSA_MUTE_VALUE:-${WHISPRTALK_ALSA_MUTE_VALUE:-0,0}}"
  ALSA_GAIN_NUMID="${WHISPRFLOW_ALSA_GAIN_NUMID:-${WHISPRTALK_ALSA_GAIN_NUMID:-}}"
  ALSA_GAIN_VALUE="${WHISPRFLOW_ALSA_GAIN_VALUE:-${WHISPRTALK_ALSA_GAIN_VALUE:-63,63}}"
  BUTTON_PORT="${WHISPRFLOW_BUTTON_PORT:-${WHISPRTALK_BUTTON_PORT:-analog-input-rear-mic}}"
  BUTTON_VOLUME="${WHISPRFLOW_BUTTON_VOLUME:-${WHISPRTALK_BUTTON_VOLUME:-46%}}"

  if [[ -n "$ALSA_CARD" && -n "$ALSA_MUTE_NUMID" ]]; then
    amixer -c "$ALSA_CARD" cset "numid=$ALSA_MUTE_NUMID" "$ALSA_MUTE_VALUE" >/dev/null 2>&1 || true
  fi
  if [[ -n "$ALSA_CARD" && -n "$ALSA_GAIN_NUMID" ]]; then
    amixer -c "$ALSA_CARD" cset "numid=$ALSA_GAIN_NUMID" "$ALSA_GAIN_VALUE" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BUTTON_DEVICE" ]]; then
    pactl set-source-port "$BUTTON_DEVICE" "$BUTTON_PORT" >/dev/null 2>&1 || true
    pactl set-source-volume "$BUTTON_DEVICE" "$BUTTON_VOLUME" >/dev/null 2>&1 || true
  fi

  HUD_ENABLED="${WHISPRFLOW_HUD:-${WHISPRTALK_HUD:-1}}"
  if [[ "$HUD_ENABLED" != "0" && -n "${DISPLAY:-}" && -f "$ROOT/hud.py" ]]; then
    if [[ -f "$HUD_PIDFILE" ]] && kill -0 "$(cat "$HUD_PIDFILE")" >/dev/null 2>&1; then
      kill "$(cat "$HUD_PIDFILE")" >/dev/null 2>&1 || true
    fi
    : >"$ROOT/hud.txt"
    nohup /usr/bin/python3 "$ROOT/hud.py" "$ROOT/hud.txt" >"$HUD_LOG" 2>&1 &
    echo "$!" >"$HUD_PIDFILE"
  fi

  if ! curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
    if [[ ! -x "$SERVER" ]]; then
      echo "missing whisper-server: $SERVER" >&2
      exit 1
    fi
    if [[ ! -f "$MODEL" ]]; then
      echo "missing local Whisper model: $MODEL" >&2
      exit 1
    fi
    mkdir -p "$ROOT"
    nohup "$SERVER" \
      --model "$MODEL" \
      --host 127.0.0.1 \
      --port "$PORT" \
      --threads "$(nproc)" \
      --language en \
      >"$LOG" 2>&1 &
    echo "$!" >"$PIDFILE"

    for _ in {1..900}; do
      if curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
        break
      fi
      if ! kill -0 "$(cat "$PIDFILE")" >/dev/null 2>&1; then
        echo "whisper-server exited during startup; see $LOG" >&2
        exit 1
      fi
      sleep 0.1
    done

    if ! curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
      echo "whisper-server did not become ready; see $LOG" >&2
      exit 1
    fi
  fi
fi

source "$ROOT/.venv/bin/activate"
exec python "$ROOT/whisprflow.py" "$@"
