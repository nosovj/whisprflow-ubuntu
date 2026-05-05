#!/usr/bin/env bash
set -euo pipefail

echo "PulseAudio/PipeWire sources:"
if command -v pactl >/dev/null 2>&1; then
  pactl list short sources
  echo
  printf "Default source: "
  pactl get-default-source 2>/dev/null || true
else
  echo "pactl not found"
fi

echo
echo "Python sounddevice devices:"
if [[ -x ".venv/bin/python" ]]; then
  .venv/bin/python - <<'PY'
import sounddevice as sd
print(sd.query_devices())
PY
elif command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY'
try:
    import sounddevice as sd
except Exception as exc:
    raise SystemExit(f"sounddevice unavailable: {exc}")
print(sd.query_devices())
PY
else
  echo "python3 not found"
fi
