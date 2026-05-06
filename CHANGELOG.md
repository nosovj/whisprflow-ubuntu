# Changelog

## v0.3.6

- Removed `max_recording_sec` from defaults, example config, docs, and runtime.
- Streaming dictation now continues while the button remains active and stops on button release or speech/silence logic.

## v0.3.4

- Added clearer source-test diagnostics when the configured button input stays flat.
- Reported likely physical input path issues when another microphone only hears weak acoustic click noise.

## v0.3.3

- Added `whisprflowctl test sources --prep-seconds 3`.
- Ranked all PulseAudio/PipeWire input sources by button-like spike strength.
- Applied the same button audio tuning in CLI diagnostics that runtime startup applies.
- Made missing `pactl` or `amixer` non-fatal for best-effort diagnostics.

## v0.3.2

- Added countdown mode for non-interactive guided setup.
- Made `whisprflowctl setup wizard --no-prompt --prep-seconds N` useful from API-driven or scripted sessions.

## v0.3.1

- Improved guided wizard timing.
- Added prompt-gated setup phases and live-meter-oriented diagnostic flow.

## v0.3.0

- Added the `whisprflowctl` management CLI.
- Added config, service, model, OpenWhispr, doctor, summary, calibration, and test commands.
