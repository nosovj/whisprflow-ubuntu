# whisprflow-ubuntu

Unofficial WhisprFlow-style dictation for Ubuntu/Linux. Hold the audio-jack button to record, pause after speaking, then transcribe through local OpenWhispr and type into the focused window.

Released under the Unlicense. Use it for anything.

Release notes live in [CHANGELOG.md](CHANGELOG.md).

## Install

Requires Python 3.10+, Git, curl, and Node.js/npm for OpenWhispr. The installer reads OpenWhispr's `package.json` and uses `nvm` when available to install the required Node major version. Current OpenWhispr requires Node.js 24+.

```bash
git clone https://github.com/nosovj/whisprflow-ubuntu.git ~/whisprflow-ubuntu
cd ~/whisprflow-ubuntu
./install.sh
```

To install deps and immediately start the user service:

```bash
./install.sh --start
```

To install and run the guided hardware/setup wizard:

```bash
./install.sh --setup
```

The installer:

- installs Ubuntu apt packages for audio, venvs, X11 typing, and clipboard fallback
- adds `wtype` on Wayland when available
- clones or updates OpenWhispr in `~/openwhispr`
- checks out pinned OpenWhispr ref `dac4a1ba` by default
- installs the Node.js major version required by OpenWhispr when `nvm` is available
- downloads OpenWhispr whisper.cpp server binaries with `npm run download:whisper-cpp`
- downloads the default STT model to `~/.cache/openwhispr/whisper-models/ggml-base.bin`
- creates `.venv`
- installs Python deps from `requirements.txt`
- installs `whisprflowctl` into `~/.local/bin`
- creates `~/.config/whisprflow/config.json`
- installs `~/.config/systemd/user/whisprflow.service`
- installs `~/.config/autostart/whisprflow.desktop`
- optionally runs `whisprflowctl setup wizard` with `--setup`

To skip OpenWhispr/model installation:

```bash
./install.sh --no-openwhispr
```

To use a different OpenWhispr ref:

```bash
OPENWHISPR_REF=main ./install.sh
```

Local transcription uses the OpenWhispr/whisper.cpp-compatible server. `run.sh` expects:

```text
~/openwhispr/dist/linux-unpacked/resources/bin/whisper-server-linux-x64
~/.cache/openwhispr/whisper-models/ggml-base.bin
```

Override the model path with:

```bash
WHISPRFLOW_MODEL=/path/to/ggml-model.bin ~/whisprflow-ubuntu/run.sh
```

To install the larger turbo model instead of the default base model:

```bash
./install.sh --model=large-v3-turbo
```

## Configure Key

```bash
~/whisprflow-ubuntu/run.sh --capture-key
```

Press the macropad button once. The key is saved to:

```text
~/.config/whisprflow/config.json
```

To find PulseAudio/PipeWire source names for `button_device` and `mic_device`:

```bash
whisprflowctl devices
```

Useful CLI commands:

```bash
whisprflowctl doctor
whisprflowctl summary
whisprflowctl config validate
whisprflowctl config show
whisprflowctl config set trigger audio_button
whisprflowctl config set button_device alsa_input.example
whisprflowctl config unset mic_device
whisprflowctl test button
whisprflowctl test mic
whisprflowctl test sources --prep-seconds 3
whisprflowctl test button --meter
whisprflowctl test mic --meter
whisprflowctl calibrate
whisprflowctl service restart
whisprflowctl logs -n 120
whisprflowctl model list
whisprflowctl model install large-v3-turbo
whisprflowctl openwhispr pin dac4a1ba
```

Guided setup:

```bash
whisprflowctl setup wizard
```

This checks the install, shows current config, waits for Enter before each phase, asks you to press the audio button, asks you to speak into the mic, then prints measured levels and recommended thresholds. Use `--no-prompt` for scripts.

For non-interactive shells, use a countdown before each phase:

```bash
whisprflowctl setup wizard --no-prompt --prep-seconds 3
```

To write recommended thresholds and restart the service:

```bash
whisprflowctl calibrate --apply
```

## Run

```bash
~/whisprflow-ubuntu/run.sh
```

Hold the configured button, speak, release. The transcript is pasted into the currently focused app.

The installed setup runs as a user service:

```bash
systemctl --user status whisprflow.service
systemctl --user restart whisprflow.service
journalctl --user -u whisprflow.service -f
```

## Config

Default config shape. Runtime fills path values under `~/whisprflow-ubuntu` when unset.

```json
{
  "provider": "local_openwhispr",
  "trigger": "keyboard",
  "hotkey": "<f9>",
  "button_device": "",
  "button_threshold": 2600,
  "button_peak_threshold": 7800,
  "button_peak_min_average": 2200,
  "button_press_chunks": 2,
  "button_debug": false,
  "button_release_threshold": 2200,
  "button_release_below_sec": 0.5,
  "button_chunk_size": 1600,
  "button_latency_msec": 20,
  "button_debounce_sec": 1.5,
  "button_rearm_threshold": 700,
  "button_rearm_peak_threshold": 2000,
  "button_rearm_chunks": 10,
  "mic_device": "",
  "mic_channels": 2,
  "mic_channel": 0,
  "mic_preroll_enabled": false,
  "mic_preroll_sec": 0.8,
  "mic_speech_threshold": 600,
  "mic_speech_peak_threshold": 1500,
  "mic_speech_peak_min_average": 150,
  "mic_silence_stop_sec": 1.0,
  "mic_no_speech_stop_sec": 4.0,
  "mic_min_mean_abs": 220,
  "streaming_phrases": true,
  "phrase_preroll_sec": 0.4,
  "phrase_silence_sec": 0.7,
  "phrase_session_silence_stop_sec": 2.4,
  "phrase_min_duration_sec": 0.25,
  "mic_latency_msec": 20,
  "button_stop_mode": "silence",
  "sample_rate": 16000,
  "channels": 1,
  "model": "whisper-1",
  "local_url": "http://127.0.0.1:8180/inference",
  "language": null,
  "min_duration_sec": 0.3,
  "paste_method": "auto",
  "play_beeps": true,
  "release_tail_sec": 0.2,
  "keep_failed_wav": null,
  "status_file": null,
  "hud_file": null,
  "hud_preview_chars": 48
}
```

`paste_method` accepts `auto`, `xdotool`, `wtype`, `ydotool`, or `clipboard`.

`provider` accepts `local_openwhispr` or `openai`. `local_openwhispr` expects a running whisper.cpp-compatible server at `local_url`. `openai` requires `OPENAI_API_KEY`.

`trigger` accepts `audio_button` or `keyboard`. `audio_button` monitors a PulseAudio/PipeWire source and treats high amplitude as button down.

The audio-jack button behaves like a pulse with a long electrical decay, not a clean keyboard hold. `button_rearm_*` requires the button source to return to idle before another recording can start.

Conky reads `status_file` for generic state. The floating HUD reads `hud_file` and only shows the latest finalized phrase briefly after it is pasted.

On X11, `auto` prefers `xdotool`, then clipboard. On Wayland, `auto` prefers `wtype`, then `ydotool`, then clipboard.

## Tested Setup

This repo was built against one Ubuntu desktop setup:

- OS: Ubuntu 22.04.5 LTS (`jammy`), kernel `6.8.0-110-generic`
- Speech mic hardware: [Samson G-Track Pro USB condenser microphone/audio interface](https://www.amazon.com/dp/B075KL6ZLC)
- PTT switch hardware: generic momentary push button wired into an audio input. The tested setup repurposed the button from a [dual-monitor DisplayPort KVM switch](https://www.amazon.com/dp/B0DG4S4L5D).
- Audio-jack push button source: `alsa_input.pci-0000_00_1f.3.analog-stereo`
- Button source port: `analog-input-rear-mic`
- Speech mic: `alsa_input.usb-Samson_Technologies_Samson_G-Track_Pro_A7F52D1227153B00-00.analog-stereo`
- Paste path: X11 `xdotool`
- Transcription: local OpenWhispr whisper.cpp-compatible server at `http://127.0.0.1:8180/inference`
- GPU on tested machine: NVIDIA RTX 5090
- STT models present: `ggml-base.bin`, `ggml-large-v3-turbo.bin`
- STT model used by default `run.sh`: `$HOME/.cache/openwhispr/whisper-models/ggml-base.bin`

Working config from that machine:

```json
{
  "provider": "local_openwhispr",
  "trigger": "audio_button",
  "hotkey": "o",
  "button_device": "alsa_input.pci-0000_00_1f.3.analog-stereo",
  "button_threshold": 2600,
  "button_peak_threshold": 7800,
  "button_peak_min_average": 2200,
  "button_press_chunks": 2,
  "button_release_threshold": 0,
  "button_release_below_sec": 999,
  "button_latency_msec": 20,
  "button_debounce_sec": 1.5,
  "button_rearm_threshold": 700,
  "button_rearm_peak_threshold": 2000,
  "button_rearm_chunks": 10,
  "mic_device": "alsa_input.usb-Samson_Technologies_Samson_G-Track_Pro_A7F52D1227153B00-00.analog-stereo",
  "mic_channels": 2,
  "mic_channel": 0,
  "mic_preroll_enabled": false,
  "mic_speech_threshold": 600,
  "mic_speech_peak_threshold": 1500,
  "mic_speech_peak_min_average": 150,
  "mic_min_mean_abs": 220,
  "streaming_phrases": true,
  "phrase_preroll_sec": 0.4,
  "phrase_silence_sec": 0.7,
  "phrase_session_silence_stop_sec": 2.4,
  "local_url": "http://127.0.0.1:8180/inference",
  "paste_method": "auto"
}
```

Optional local tuning for similar audio-jack button setups:

```bash
export WHISPRFLOW_ALSA_CARD=3
export WHISPRFLOW_ALSA_MUTE_NUMID=13
export WHISPRFLOW_ALSA_MUTE_VALUE=0,0
export WHISPRFLOW_ALSA_GAIN_NUMID=11
export WHISPRFLOW_ALSA_GAIN_VALUE=63,63
export WHISPRFLOW_BUTTON_PORT=analog-input-rear-mic
export WHISPRFLOW_BUTTON_VOLUME=46%
```

## Autostart

Autostart is installed. Login starts:

- `~/.config/autostart/whisprflow.desktop`
- `~/whisprflow-ubuntu/autostart.sh`
- `~/.config/systemd/user/whisprflow.service`

The desktop entry imports GUI session variables into systemd, then restarts the service. This matters because X11 typing needs `DISPLAY`.

To re-enable manually:

```bash
systemctl --user daemon-reload
systemctl --user enable --now whisprflow.service
```

To disable autostart:

```bash
systemctl --user disable --now whisprflow.service
rm -f ~/.config/autostart/whisprflow.desktop
```

## Troubleshooting

- `OPENAI_API_KEY missing`: run through `~/whisprflow-ubuntu/run.sh` or export the variable.
- Wayland direct typing needs `wtype`. Without it, clipboard fallback may copy text and require Ctrl+V.
- Garbled X11 typing can mean the target app is dropping fast keystrokes. Raise the `xdotool` delay in `whisprflow.py`.
- No mic input usually means PulseAudio/PipeWire default input is wrong. Check Ubuntu sound settings.
- Audio button not triggering means `button_device`, `button_threshold`, or `button_peak_threshold` is wrong. Set `button_debug` to `true`, restart the service, and watch `journalctl --user -u whisprflow.service -f`.
- Run `whisprflowctl test button` to check whether button levels are detectable and get threshold recommendations.
- Run `whisprflowctl test sources --prep-seconds 3` if the configured button source stays flat. It watches all input sources and prints the source with the largest click spike.
- If source testing prints `configured button source stayed flat`, the selected audio input did not receive the electrical button signal. Check the button cable, jack, TRS/TRRS adapter wiring, selected PulseAudio/PipeWire input port, and Ubuntu Sound Settings input meter before changing thresholds.
- Run `whisprflowctl test mic` to check whether speech is too quiet, too loud, clipped, or indistinguishable from silence.
- Run `whisprflowctl config validate` before restarting after manual edits.
- `pynput` failures on Wayland can require running under X11/XWayland, depending on compositor security policy.
