# whisprflow-ubuntu

Unofficial WhisprFlow-style dictation for Ubuntu/Linux. Hold the audio-jack button to record, pause after speaking, then transcribe through local OpenWhispr and type into the focused window.

## Install

```bash
sudo apt update
sudo apt install -y python3-venv portaudio19-dev xdotool wl-clipboard xclip

mkdir -p ~/whisprtalk
python3 -m venv ~/whisprtalk/.venv
source ~/whisprtalk/.venv/bin/activate
pip install --upgrade pip
pip install sounddevice numpy pynput requests
```

Wayland users should also install `wtype` when available:

```bash
sudo apt install -y wtype
```

Local transcription uses an existing OpenWhispr/whisper.cpp-compatible server. This repo does not install OpenWhispr or download speech-to-text models yet. `run.sh` expects:

```text
~/openwhispr/dist/linux-unpacked/resources/bin/whisper-server-linux-x64
~/.cache/openwhispr/whisper-models/ggml-base.bin
```

Override the model path with:

```bash
WHISPRTALK_MODEL=/path/to/ggml-model.bin ~/whisprtalk/run.sh
```

## Configure Key

```bash
~/whisprtalk/run.sh --capture-key
```

Press the macropad button once. The key is saved to:

```text
~/.config/whisprtalk/config.json
```

## Run

```bash
~/whisprtalk/run.sh
```

Hold the configured button, speak, release. The transcript is pasted into the currently focused app.

The installed setup runs as a user service:

```bash
systemctl --user status whisprtalk.service
systemctl --user restart whisprtalk.service
journalctl --user -u whisprtalk.service -f
```

## Config

Default config:

```json
{
  "hotkey": "<f9>",
  "provider": "local_openwhispr",
  "trigger": "keyboard",
  "button_device": "",
  "button_threshold": 2600,
  "button_peak_threshold": 7800,
  "button_peak_min_average": 2200,
  "button_press_chunks": 2,
  "button_debug": false,
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
  "mic_speech_threshold": 600,
  "mic_speech_peak_threshold": 1500,
  "mic_speech_peak_min_average": 150,
  "mic_no_speech_stop_sec": 4.0,
  "mic_min_mean_abs": 220,
  "max_recording_sec": 15.0,
  "streaming_phrases": true,
  "phrase_preroll_sec": 0.4,
  "phrase_silence_sec": 0.7,
  "phrase_session_silence_stop_sec": 2.4,
  "phrase_min_duration_sec": 0.25,
  "mic_latency_msec": 20,
  "sample_rate": 16000,
  "channels": 1,
  "model": "whisper-1",
  "local_url": "http://127.0.0.1:8180/inference",
  "language": null,
  "min_duration_sec": 0.3,
  "paste_method": "auto",
  "play_beeps": true,
  "release_tail_sec": 0.4,
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

- Speech mic hardware: [Samson G-Track Pro USB condenser microphone/audio interface](https://www.amazon.com/dp/B075KL6ZLC)
- PTT switch hardware: generic momentary push button wired into an audio input. The tested setup repurposed the button from a [dual-monitor DisplayPort KVM switch](https://www.amazon.com/dp/B0DG4S4L5D).
- Audio-jack push button source: `alsa_input.pci-0000_00_1f.3.analog-stereo`
- Button source port: `analog-input-rear-mic`
- Speech mic: `alsa_input.usb-Samson_Technologies_Samson_G-Track_Pro_A7F52D1227153B00-00.analog-stereo`
- Paste path: X11 `xdotool`
- Transcription: local OpenWhispr whisper.cpp-compatible server at `http://127.0.0.1:8180/inference`
- GPU on tested machine: NVIDIA RTX 5090
- STT model used by `run.sh`: `$HOME/.cache/openwhispr/whisper-models/ggml-base.bin`

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
export WHISPRTALK_ALSA_CARD=3
export WHISPRTALK_ALSA_MUTE_NUMID=13
export WHISPRTALK_ALSA_MUTE_VALUE=0,0
export WHISPRTALK_ALSA_GAIN_NUMID=11
export WHISPRTALK_ALSA_GAIN_VALUE=63,63
export WHISPRTALK_BUTTON_PORT=analog-input-rear-mic
export WHISPRTALK_BUTTON_VOLUME=46%
```

## Autostart

Autostart is installed. Login starts:

- `~/.config/autostart/whisprtalk.desktop`
- `~/whisprtalk/autostart.sh`
- `~/.config/systemd/user/whisprtalk.service`

The desktop entry imports GUI session variables into systemd, then restarts the service. This matters because X11 typing needs `DISPLAY`.

To re-enable manually:

```bash
systemctl --user daemon-reload
systemctl --user enable --now whisprtalk.service
```

Old autostarts are disabled:

- `~/.config/autostart/voice-to-text.desktop`
- `~/.config/autostart/whisper-server.desktop`

## Troubleshooting

- `OPENAI_API_KEY missing`: run through `~/whisprtalk/run.sh` or export the variable.
- Wayland direct typing needs `wtype`. Without it, clipboard fallback may copy text and require Ctrl+V.
- Garbled X11 typing can mean the target app is dropping fast keystrokes. Raise the `xdotool` delay in `whisprtalk.py`.
- No mic input usually means PulseAudio/PipeWire default input is wrong. Check Ubuntu sound settings.
- Audio button not triggering means `button_device`, `button_threshold`, or `button_peak_threshold` is wrong. Set `button_debug` to `true`, restart the service, and watch `journalctl --user -u whisprtalk.service -f`.
- `pynput` failures on Wayland can require running under X11/XWayland, depending on compositor security policy.
