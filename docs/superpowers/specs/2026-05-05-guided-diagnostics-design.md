# Guided Diagnostics Design

## Goal

Make `whisprflowctl` useful for a real setup session, not just raw config edits. A user should be able to run guided checks, press their audio button, speak into the mic, and get plain feedback such as "button not detected", "mic too quiet", "signal clipping", or "threshold looks high".

## Commands

- `whisprflowctl summary`: print the current setup in human terms: trigger, button source, mic source, service state, model state, paste path, and common next commands.
- `whisprflowctl config validate`: check known config keys for type/value mistakes before restart.
- `whisprflowctl test button [--seconds N] [--meter]`: sample the configured button source, ask the user to press/release the button, optionally print live level lines, report idle/active levels, verdict, and recommended thresholds.
- `whisprflowctl test mic [--seconds N] [--meter]`: sample the configured speech mic, ask the user to speak, optionally print live level lines, report silence/speech levels, verdict, and recommended thresholds.
- `whisprflowctl test sources [--seconds N] [--prep-seconds N]`: monitor all PulseAudio/PipeWire input sources concurrently and rank which source had the strongest button-like spike.
- `whisprflowctl calibrate [--apply]`: run button and mic tests together. Without `--apply`, print a config patch. With `--apply`, save recommendations and restart the service.
- `whisprflowctl setup wizard [--no-prompt] [--prep-seconds N]`: conversational wrapper around `doctor`, `summary`, `test button`, `test mic`, optional apply, and service restart. In an interactive terminal it waits for Enter before button and mic phases. In non-interactive shells it prints a countdown before each phase.

## UX Rules

The CLI should avoid raw-only output. Every diagnostic command prints:

- what it is listening to,
- what the user should do now,
- when the timed test starts,
- measured level table,
- verdict,
- recommended config values,
- exact command to apply or inspect settings.

The first version stays terminal-native. It uses normal prompts and readable sections, not a full Textual/Ink dashboard. A full TUI can come later after the measurement model is proven.

## Measurement Model

Button and mic sampling use PulseAudio/PipeWire through `parecord`, matching the runtime audio-button path. Samples are 16-bit mono PCM at the configured sample rate. Each chunk records mean absolute amplitude and peak.

Button analysis splits chunks into idle and active groups by taking the quiet lower third and loud upper third. It reports whether the observed active signal clearly exceeds idle and recommends conservative thresholds between idle and active.

Mic analysis does the same for silence and speech. It warns if speech is too quiet, indistinguishable from silence, or near clipping.

## Safety

`config set` should validate known keys so numeric config cannot accidentally become a string. `config validate` should catch existing bad values. `calibrate --apply` only writes known recommendation keys and preserves unrelated config.

## Tests

Unit tests cover pure analysis and validation. Command tests mock audio sampling and command execution so CI never needs real audio hardware.
