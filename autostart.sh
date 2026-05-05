#!/usr/bin/env bash
set -euo pipefail

systemctl --user import-environment DISPLAY XAUTHORITY XDG_SESSION_TYPE WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS || true
exec systemctl --user restart whisprtalk.service
