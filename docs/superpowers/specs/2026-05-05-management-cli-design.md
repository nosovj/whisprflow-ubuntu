# Management CLI Design

## Goal

Add a small `whisprflowctl` command so users can install, inspect, configure, debug, and service WhisprFlow without hand-editing files or remembering systemd/journal commands.

## Scope

Batch 1 covers the high-value operational commands:

- `setup` to run the installer.
- `doctor` to report missing runtime pieces.
- `devices` to list audio sources.
- `config show|get|set|unset` to manage `~/.config/whisprflow/config.json`.
- `service status|start|stop|restart` to wrap the user service.
- `logs` to wrap `journalctl --user`.
- `model list|install` to inspect and fetch whisper.cpp model files.
- `openwhispr install|pin` to reinstall or pin the local OpenWhispr checkout.

Out of scope for this batch: an interactive setup wizard, calibration UI, model benchmarking, service health daemon, or desktop notifications.

## Architecture

`whisprflowctl.py` is a standalone Python CLI beside `whisprflow.py`. It uses `argparse`, the same config path convention as runtime, and shell command wrappers for existing installer/systemd/journal/audio scripts. The installer symlinks it to `~/.local/bin/whisprflowctl`.

The CLI keeps runtime behavior unchanged. It edits only explicit config overrides; unset keys fall back to `whisprflow.py` defaults.

## Error Handling

Commands return the child process exit code where possible. Config values parse through JSON first, so booleans, numbers, `null`, arrays, and strings are all supported. `doctor` returns non-zero when warnings exist so scripts can detect an incomplete install.

## Testing

Unit tests cover config mutation, service command construction, model install routing, OpenWhispr pin routing, and doctor success behavior under mocked dependencies. Packaging tests verify README, installer, and CI references. CI runs tests under Xvfb because `pynput` imports need display support.
