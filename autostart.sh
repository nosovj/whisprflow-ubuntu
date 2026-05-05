#!/usr/bin/env bash
set -euo pipefail

systemctl --user import-environment DISPLAY XAUTHORITY XDG_SESSION_TYPE WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS || true
SERVICE="${WHISPRFLOW_SERVICE:-whisprflow.service}"
if ! systemctl --user cat "$SERVICE" >/dev/null 2>&1 && systemctl --user cat whisprtalk.service >/dev/null 2>&1; then
  SERVICE="whisprtalk.service"
fi
exec systemctl --user restart "$SERVICE"
