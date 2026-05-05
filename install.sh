#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CONFIG_HOME/whisprflow"
CONFIG_FILE="$CONFIG_DIR/config.json"
LEGACY_CONFIG_FILE="$CONFIG_HOME/whisprtalk/config.json"
SYSTEMD_DIR="$CONFIG_HOME/systemd/user"
AUTOSTART_DIR="$CONFIG_HOME/autostart"

INSTALL_APT=1
INSTALL_SERVICE=1
START_SERVICE=0

for arg in "$@"; do
  case "$arg" in
    --no-apt) INSTALL_APT=0 ;;
    --no-service) INSTALL_SERVICE=0 ;;
    --start) START_SERVICE=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./install.sh [--no-apt] [--no-service] [--start]

Installs Python deps, creates config, and installs user service/autostart.
It does not install OpenWhispr or download STT models.
EOF
      exit 0
      ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$INSTALL_APT" == "1" ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    packages=(python3-venv portaudio19-dev xdotool wl-clipboard xclip)
    session_type="${XDG_SESSION_TYPE:-}"
    if [[ "$session_type" == "wayland" ]] && apt-cache show wtype >/dev/null 2>&1; then
      packages+=(wtype)
    fi
    sudo apt update
    sudo apt install -y "${packages[@]}"
  else
    echo "apt-get not found; install system deps manually for your distro" >&2
  fi
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"

mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_FILE" ]]; then
  if [[ -f "$LEGACY_CONFIG_FILE" ]]; then
    cp "$LEGACY_CONFIG_FILE" "$CONFIG_FILE"
    echo "copied legacy config: $LEGACY_CONFIG_FILE -> $CONFIG_FILE"
  else
    cp "$ROOT/config.example.json" "$CONFIG_FILE"
    echo "created config: $CONFIG_FILE"
  fi
fi

if [[ "$INSTALL_SERVICE" == "1" ]]; then
  mkdir -p "$SYSTEMD_DIR" "$AUTOSTART_DIR"
  sed "s#__ROOT__#$ROOT#g" "$ROOT/systemd/whisprflow.service" >"$SYSTEMD_DIR/whisprflow.service"
  sed "s#__ROOT__#$ROOT#g" "$ROOT/autostart/whisprflow.desktop" >"$AUTOSTART_DIR/whisprflow.desktop"
  chmod 644 "$SYSTEMD_DIR/whisprflow.service" "$AUTOSTART_DIR/whisprflow.desktop"
  systemctl --user daemon-reload
  systemctl --user enable whisprflow.service
  if [[ "$START_SERVICE" == "1" ]]; then
    systemctl --user restart whisprflow.service
  fi
fi

missing=0
server="$HOME/openwhispr/dist/linux-unpacked/resources/bin/whisper-server-linux-x64"
model="${WHISPRFLOW_MODEL:-$HOME/.cache/openwhispr/whisper-models/ggml-base.bin}"
if [[ ! -x "$server" ]]; then
  echo "missing OpenWhispr server: $server" >&2
  missing=1
fi
if [[ ! -f "$model" ]]; then
  echo "missing STT model: $model" >&2
  missing=1
fi

echo
echo "Installed WhisprFlow files in: $ROOT"
echo "Config: $CONFIG_FILE"
if [[ "$INSTALL_SERVICE" == "1" ]]; then
  echo "Service: systemctl --user status whisprflow.service"
fi
if [[ "$missing" == "1" ]]; then
  echo "OpenWhispr/model missing; install those or set WHISPRFLOW_MODEL before running." >&2
fi
