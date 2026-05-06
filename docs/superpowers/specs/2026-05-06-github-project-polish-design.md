# GitHub Project Polish Design

## Goal

Make WhisprFlow easier to evaluate and install from GitHub without adding distro packaging.

## Scope

- Add a `CHANGELOG.md` covering public release tags `v0.3.0` through `v0.3.4`.
- Add an installer flag, `./install.sh --setup`, that runs `whisprflowctl setup wizard` after files, config, service files, OpenWhispr, and Python dependencies are installed.
- Document the tested Ubuntu/Samson/audio-button setup and the current hardware diagnosis flow more clearly.
- Add packaging tests that protect installer and documentation behavior.

## Out Of Scope

- No `.deb`, PPA, Homebrew, Flatpak, AppImage, or binary release packaging.
- No new runtime transcription behavior.
- No changes to the user's current config.

## Installer Behavior

`install.sh --setup` will run `"$ROOT/.venv/bin/python" "$ROOT/whisprflowctl.py" setup wizard` after service files are installed. If `--start` is also passed, the service still restarts after the setup wizard so calibration/config changes can be picked up.

The flag is explicit because the wizard is interactive by default. Non-interactive users can keep using `whisprflowctl setup wizard --no-prompt --prep-seconds 3` after install.

## Documentation Behavior

The README should present the project as a GitHub-installable Linux tool:

- clone and run `./install.sh`
- optionally run `./install.sh --setup`
- run `whisprflowctl setup wizard`
- diagnose a flat button signal with `whisprflowctl test sources --prep-seconds 3`
- understand that a flat configured source means the physical signal is not reaching the selected input

The tested setup section should remain concrete: Ubuntu 22.04.5, Samson G-Track Pro, built-in rear mic input for the button, local OpenWhispr, and the supported model names.

## Testing

Unit/packaging tests should assert:

- installer help documents `--setup`
- installer invokes `setup wizard` when `--setup` is present
- README references `CHANGELOG.md`, `--setup`, and flat-source diagnostics
- changelog documents the current tags

Full verification remains:

- Python unittest suite
- Xvfb unittest suite
- shell syntax check
- Python AST parse
- secret grep
- CI green on `main` and release tag
