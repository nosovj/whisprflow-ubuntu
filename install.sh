#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CONFIG_HOME/whisprflow"
CONFIG_FILE="$CONFIG_DIR/config.json"
LEGACY_CONFIG_FILE="$CONFIG_HOME/whisprtalk/config.json"
SYSTEMD_DIR="$CONFIG_HOME/systemd/user"
AUTOSTART_DIR="$CONFIG_HOME/autostart"
OPENWHISPR_ROOT="${OPENWHISPR_ROOT:-$HOME/openwhispr}"
OPENWHISPR_REPO="${OPENWHISPR_REPO:-https://github.com/OpenWhispr/openwhispr.git}"
MODEL_NAME="${WHISPRFLOW_MODEL_NAME:-base}"
MODEL_DIR="${WHISPRFLOW_MODEL_DIR:-$HOME/.cache/openwhispr/whisper-models}"

INSTALL_APT=1
INSTALL_SERVICE=1
INSTALL_OPENWHISPR=1
START_SERVICE=0

for arg in "$@"; do
  case "$arg" in
    --no-apt) INSTALL_APT=0 ;;
    --no-service) INSTALL_SERVICE=0 ;;
    --no-openwhispr) INSTALL_OPENWHISPR=0 ;;
    --openwhispr-root=*) OPENWHISPR_ROOT="${arg#*=}" ;;
    --model=*) MODEL_NAME="${arg#*=}" ;;
    --start) START_SERVICE=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./install.sh [--no-apt] [--no-openwhispr] [--no-service] [--start]

Installs Python deps, OpenWhispr server files, default STT model, config,
and user service/autostart.

Options:
  --no-apt                 skip Ubuntu apt package installation
  --no-openwhispr          skip OpenWhispr clone/update and STT model download
  --no-service             skip systemd/autostart installation
  --start                  restart whisprflow.service after install
  --openwhispr-root=PATH   OpenWhispr checkout path (default: ~/openwhispr)
  --model=NAME             STT model: base or large-v3-turbo
EOF
      exit 0
      ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$INSTALL_APT" == "1" ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    packages=(python3-venv portaudio19-dev xdotool wl-clipboard xclip git curl)
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

model_file_for_name() {
  case "$1" in
    base) echo "ggml-base.bin" ;;
    large-v3-turbo|turbo) echo "ggml-large-v3-turbo.bin" ;;
    ggml-*.bin) echo "$1" ;;
    *) echo "unknown model: $1" >&2; return 2 ;;
  esac
}

openwhispr_required_node_major() {
  local package_json="$OPENWHISPR_ROOT/package.json"
  if [[ ! -f "$package_json" ]]; then
    echo 18
    return 0
  fi
  python3 - "$package_json" <<'PY'
import json
import re
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    package = json.load(f)
engine = str(package.get("engines", {}).get("node", ">=18"))
match = re.search(r">=\s*(\d+)", engine)
print(match.group(1) if match else "18")
PY
}

activate_node_for_openwhispr() {
  local required_major="$1"
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    local current_major
    current_major="$(node -p 'process.versions.node.split(".")[0]')"
    if [[ "$current_major" -ge "$required_major" ]]; then
      return 0
    fi
  fi

  if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    . "$HOME/.nvm/nvm.sh"
    nvm install "$required_major"
    nvm use "$required_major"
    return 0
  fi

  echo "Node.js >=$required_major and npm are required to install OpenWhispr; rerun with --no-openwhispr to skip" >&2
  return 1
}

require_node_for_openwhispr() {
  local required_major
  required_major="$(openwhispr_required_node_major)"
  activate_node_for_openwhispr "$required_major"
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "node and npm are required to install OpenWhispr; rerun with --no-openwhispr to skip" >&2
    return 1
  fi
  local major
  major="$(node -p 'process.versions.node.split(".")[0]')"
  if [[ "$major" -lt "$required_major" ]]; then
    echo "Node.js >=$required_major required to install OpenWhispr; found $(node --version)" >&2
    return 1
  fi
}

install_openwhispr() {
  if [[ -d "$OPENWHISPR_ROOT/.git" ]]; then
    git -C "$OPENWHISPR_ROOT" pull --ff-only
  elif [[ -e "$OPENWHISPR_ROOT" ]]; then
    echo "OpenWhispr root exists but is not a git checkout: $OPENWHISPR_ROOT" >&2
    return 1
  else
    git clone "$OPENWHISPR_REPO" "$OPENWHISPR_ROOT"
  fi
  require_node_for_openwhispr
  npm --prefix "$OPENWHISPR_ROOT" install
  npm --prefix "$OPENWHISPR_ROOT" run download:whisper-cpp
}

download_model() {
  local model_file
  model_file="$(model_file_for_name "$MODEL_NAME")"
  mkdir -p "$MODEL_DIR"
  local model_path="$MODEL_DIR/$model_file"
  if [[ -f "$model_path" ]]; then
    echo "STT model already exists: $model_path"
    return 0
  fi
  curl -L --fail --continue-at - \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$model_file" \
    -o "$model_path"
}

if [[ "$INSTALL_OPENWHISPR" == "1" ]]; then
  install_openwhispr
  download_model
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
if [[ -x "$OPENWHISPR_ROOT/dist/linux-unpacked/resources/bin/whisper-server-linux-x64" ]]; then
  server="$OPENWHISPR_ROOT/dist/linux-unpacked/resources/bin/whisper-server-linux-x64"
else
  server="$OPENWHISPR_ROOT/resources/bin/whisper-server-linux-x64"
fi
model="${WHISPRFLOW_MODEL:-$MODEL_DIR/$(model_file_for_name "$MODEL_NAME")}"
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
  echo "OpenWhispr/model missing; rerun ./install.sh or set WHISPRFLOW_MODEL before running." >&2
fi
