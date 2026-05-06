import json
import os
import struct
import tempfile
import unittest
import wave
from unittest import mock

import numpy as np

import whisprflow


class LocalOpenWhisprTests(unittest.TestCase):
    def test_local_whisper_parses_json_text_response(self):
        response = mock.Mock()
        response.text = json.dumps({"text": " hello\nworld "})
        response.headers = {"content-type": "application/json"}
        response.raise_for_status.return_value = None

        with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
            wav.write(b"RIFFfake")
            wav.flush()
            with mock.patch("whisprflow.requests.post", return_value=response) as post:
                text = whisprflow.transcribe_local_openwhispr(
                    wav.name,
                    {
                        "local_url": "http://127.0.0.1:8180/inference",
                        "language": None,
                    },
                )

        self.assertEqual(text, "hello world")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:8180/inference")
        self.assertEqual(kwargs["data"]["response_format"], "json")
        self.assertNotIn("language", kwargs["data"])
        self.assertEqual(kwargs["timeout"], 300)

    def test_transcribe_dispatches_to_local_without_api_key(self):
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with mock.patch("whisprflow.transcribe_local_openwhispr", return_value="local text") as local:
                text = whisprflow.transcribe(
                    "/tmp/fake.wav",
                    {"provider": "local_openwhispr", "local_url": "http://127.0.0.1:8180/inference"},
                )
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key

        self.assertEqual(text, "local text")
        local.assert_called_once()

    def test_local_error_response_raises_instead_of_pasting_json(self):
        with self.assertRaisesRegex(RuntimeError, "failed to read audio data"):
            whisprflow.parse_local_response('{"error":"failed to read audio data"}', "application/json")

    def test_noise_transcripts_are_skipped(self):
        self.assertTrue(whisprflow.is_noise_transcript("Thank you."))
        self.assertTrue(whisprflow.is_noise_transcript("."))
        self.assertTrue(whisprflow.is_noise_transcript("-"))
        self.assertTrue(whisprflow.is_noise_transcript("(clicks tongue)"))
        self.assertTrue(whisprflow.is_noise_transcript("(gentle music)"))
        self.assertTrue(whisprflow.is_noise_transcript("[applause]"))
        self.assertTrue(whisprflow.is_noise_transcript("[typing]"))
        self.assertEqual(whisprflow.clean_transcript("li[applause]ke"), "like")
        self.assertFalse(whisprflow.is_noise_transcript("Testing one two three."))

    def test_hud_preview_text_is_single_line_and_capped(self):
        text = whisprflow.hud_preview_text("Testing\none two three four five", max_chars=18)

        self.assertEqual(text, "Testing one two...")

    def test_hud_preview_text_hides_empty_text(self):
        self.assertEqual(whisprflow.hud_preview_text("   "), "")


class AudioButtonTests(unittest.TestCase):
    def test_default_config_has_no_recording_duration_cap(self):
        self.assertNotIn("max_recording_sec", whisprflow.DEFAULT_CONFIG)

    def test_average_amplitude_reads_int16_samples(self):
        data = struct.pack("<4h", -100, 200, -300, 400)

        self.assertEqual(whisprflow.average_amplitude(data), 250)
        self.assertEqual(whisprflow.audio_levels(data), (250, 400))

    def test_button_monitor_fires_press_and_release_after_debounce(self):
        events = []
        detector = whisprflow.AudioButtonDetector(
            threshold=1000,
            peak_threshold=3000,
            peak_min_average=900,
            press_chunks=1,
            release_threshold=800,
            debounce_sec=0.3,
            release_below_sec=0.0,
            on_press=lambda: events.append("press") or True,
            on_release=lambda: events.append("release"),
            clock=lambda: times.pop(0),
        )
        times = [0.0, 0.4, 0.8]

        detector.process_amplitude(100)
        detector.process_amplitude(2000)
        detector.process_amplitude(100)

        self.assertEqual(events, ["press", "release"])

    def test_button_monitor_waits_for_sustained_low_before_release(self):
        events = []
        detector = whisprflow.AudioButtonDetector(
            threshold=1000,
            peak_threshold=3000,
            peak_min_average=900,
            press_chunks=1,
            release_threshold=800,
            debounce_sec=0.0,
            release_below_sec=0.5,
            on_press=lambda: events.append("press") or True,
            on_release=lambda: events.append("release"),
            clock=lambda: times.pop(0),
        )
        times = [0.0, 0.1, 0.2, 0.7]

        detector.process_amplitude(1200)
        detector.process_amplitude(700)
        detector.process_amplitude(900)
        detector.process_amplitude(700)

        self.assertEqual(events, ["press"])

    def test_button_monitor_fires_on_peak_click(self):
        events = []
        detector = whisprflow.AudioButtonDetector(
            threshold=3000,
            peak_threshold=7000,
            peak_min_average=2000,
            press_chunks=2,
            release_threshold=800,
            debounce_sec=0.0,
            release_below_sec=0.0,
            on_press=lambda: events.append("press") or True,
            on_release=lambda: events.append("release"),
            clock=lambda: times.pop(0),
        )
        times = [0.0, 0.1, 0.2]

        detector.process_levels(2100, 8000)
        detector.process_levels(2150, 8200)
        detector.process_levels(100, 200)

        self.assertEqual(events, ["press", "release"])

    def test_button_monitor_ignores_isolated_peak_noise(self):
        events = []
        detector = whisprflow.AudioButtonDetector(
            threshold=2300,
            peak_threshold=9000,
            peak_min_average=2200,
            press_chunks=2,
            release_threshold=800,
            debounce_sec=0.0,
            release_below_sec=0.0,
            on_press=lambda: events.append("press") or True,
            on_release=lambda: events.append("release"),
            clock=lambda: 0.0,
        )

        detector.process_levels(2050, 12000)
        detector.process_levels(2050, 6000)

        self.assertEqual(events, [])

    def test_button_monitor_requires_idle_rearm_after_press_decay(self):
        events = []
        now = [0.0]
        detector = whisprflow.AudioButtonDetector(
            threshold=120,
            peak_threshold=500,
            peak_min_average=90,
            press_chunks=3,
            release_threshold=0,
            debounce_sec=1.5,
            release_below_sec=999,
            on_press=lambda: events.append("press") or True,
            on_release=lambda: events.append("release"),
            clock=lambda: now[0],
            rearm_threshold=100,
            rearm_peak_threshold=450,
            rearm_chunks=3,
            start_armed=False,
        )

        for level in [65, 66, 64]:
            detector.process_levels(level, 200)
            now[0] += 0.1
        for level in [16000, 12000, 8000, 4000, 2000, 1000, 500, 200, 130]:
            detector.process_levels(level, 16000)
            now[0] += 0.5
        detector.require_rearm()
        now[0] += 2.0
        for level in [5000, 4000, 2000, 500, 150, 120]:
            detector.process_levels(level, 16000)
            now[0] += 0.5

        self.assertEqual(events, ["press"])

        for level in [80, 75, 70]:
            detector.process_levels(level, 250)
            now[0] += 0.1
        for level in [16000, 16000, 16000]:
            detector.process_levels(level, 16000)
            now[0] += 0.1

        self.assertEqual(events, ["press", "press"])

    def test_ring_recorder_includes_preroll_when_started(self):
        recorder = whisprflow.RingRecorder(sample_rate=4, channels=1, preroll_sec=0.5)
        recorder._recording = False
        recorder._accept_frame(np.array([[1], [2]], dtype=np.int16))

        recorder.start()
        recorder._accept_frame(np.array([[3], [4]], dtype=np.int16))
        audio, duration = recorder.stop()

        self.assertEqual(audio.reshape(-1).tolist(), [1, 2, 3, 4])
        self.assertEqual(duration, 1.0)

    def test_parecord_ring_recorder_accepts_raw_bytes(self):
        recorder = whisprflow.ParecordRingRecorder(sample_rate=4, channels=1, preroll_sec=0.5, device="mic")
        recorder._accept_raw(struct.pack("<2h", 10, 20))

        recorder.start()
        recorder._accept_raw(struct.pack("<2h", 30, 40))
        audio, duration = recorder.stop()

        self.assertEqual(audio.reshape(-1).tolist(), [10, 20, 30, 40])
        self.assertEqual(duration, 1.0)

    def test_ring_recorder_marks_autostop_after_speech_then_silence(self):
        now = [0.0]
        recorder = whisprflow.RingRecorder(
            sample_rate=4,
            channels=1,
            preroll_sec=0.0,
            speech_threshold=100,
            silence_stop_sec=0.75,
            clock=lambda: now[0],
        )
        recorder.start()
        recorder._accept_frame(np.array([[200], [220]], dtype=np.int16))
        now[0] = 0.5
        recorder._accept_frame(np.array([[5], [8]], dtype=np.int16))

        self.assertFalse(recorder.should_auto_stop(min_duration_sec=0.3))

        now[0] = 1.0
        recorder._accept_frame(np.array([[4], [7]], dtype=np.int16))

        self.assertTrue(recorder.should_auto_stop(min_duration_sec=0.3))

    def test_ring_recorder_uses_longer_no_speech_grace(self):
        now = [0.0]
        recorder = whisprflow.RingRecorder(
            sample_rate=4,
            channels=1,
            preroll_sec=0.0,
            speech_threshold=100,
            silence_stop_sec=0.75,
            no_speech_stop_sec=3.0,
            clock=lambda: now[0],
        )
        recorder.start()
        now[0] = 1.0
        recorder._accept_frame(np.array([[4], [7]], dtype=np.int16))
        self.assertFalse(recorder.should_auto_stop(min_duration_sec=0.3))

        now[0] = 3.1
        recorder._accept_frame(np.array([[4], [7]], dtype=np.int16))
        self.assertTrue(recorder.should_auto_stop(min_duration_sec=0.3))

    def test_select_audio_channel_keeps_single_requested_channel(self):
        audio = np.array([[1, 10], [2, 20], [3, 30]], dtype=np.int16)

        selected = whisprflow.select_audio_channel(audio, 0)

        self.assertEqual(selected.reshape(-1).tolist(), [1, 2, 3])
        self.assertEqual(selected.shape, (3, 1))

    def test_wav_with_selected_channel_writes_mono_copy(self):
        original = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        original.close()
        try:
            with wave.open(original.name, "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(np.array([[1, 10], [2, 20], [3, 30]], dtype=np.int16).tobytes())

            selected_path = whisprflow.wav_with_selected_channel(original.name, 1)
            try:
                with wave.open(selected_path, "rb") as wf:
                    data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                    self.assertEqual(wf.getnchannels(), 1)
                    self.assertEqual(data.tolist(), [10, 20, 30])
            finally:
                os.unlink(selected_path)
        finally:
            os.unlink(original.name)

    def test_wav_mean_abs_measures_audio_energy(self):
        original = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        original.close()
        try:
            with wave.open(original.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(np.array([-100, 200, -300], dtype=np.int16).tobytes())

            self.assertEqual(whisprflow.wav_mean_abs(original.name), 200)
        finally:
            os.unlink(original.name)


class PhraseSegmenterTests(unittest.TestCase):
    def test_phrase_segmenter_finalizes_after_short_silence(self):
        segmenter = whisprflow.PhraseSegmenter(
            sample_rate=10,
            channels=1,
            preroll_sec=0.0,
            speech_threshold=100,
            phrase_silence_sec=0.2,
            session_silence_stop_sec=1.0,
            no_speech_stop_sec=2.0,
            min_phrase_sec=0.1,
        )

        self.assertEqual(segmenter.accept(np.array([[200], [220]], dtype=np.int16)), [])
        finalized = segmenter.accept(np.array([[0], [0]], dtype=np.int16))

        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0].reshape(-1).tolist(), [200, 220, 0, 0])
        self.assertFalse(segmenter.should_stop())

    def test_phrase_segmenter_detects_peaky_speech_below_average_threshold(self):
        segmenter = whisprflow.PhraseSegmenter(
            sample_rate=10,
            channels=1,
            preroll_sec=0.0,
            speech_threshold=600,
            phrase_silence_sec=0.2,
            session_silence_stop_sec=1.0,
            no_speech_stop_sec=2.0,
            min_phrase_sec=0.1,
            speech_peak_threshold=1500,
            speech_peak_min_average=150,
        )

        segmenter.accept(np.array([[80], [2000]], dtype=np.int16))
        finalized = segmenter.accept(np.array([[0], [0]], dtype=np.int16))

        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0].reshape(-1).tolist(), [80, 2000, 0, 0])

    def test_phrase_segmenter_keeps_preroll_before_speech(self):
        segmenter = whisprflow.PhraseSegmenter(
            sample_rate=10,
            channels=1,
            preroll_sec=0.2,
            speech_threshold=100,
            phrase_silence_sec=0.2,
            session_silence_stop_sec=1.0,
            no_speech_stop_sec=2.0,
            min_phrase_sec=0.1,
        )

        segmenter.accept(np.array([[1], [2]], dtype=np.int16))
        segmenter.accept(np.array([[200], [220]], dtype=np.int16))
        finalized = segmenter.accept(np.array([[0], [0]], dtype=np.int16))

        self.assertEqual(finalized[0].reshape(-1).tolist(), [1, 2, 200, 220, 0, 0])

    def test_phrase_segmenter_stops_after_long_silence_following_phrase(self):
        segmenter = whisprflow.PhraseSegmenter(
            sample_rate=10,
            channels=1,
            preroll_sec=0.0,
            speech_threshold=100,
            phrase_silence_sec=0.2,
            session_silence_stop_sec=0.5,
            no_speech_stop_sec=2.0,
            min_phrase_sec=0.1,
        )

        segmenter.accept(np.array([[200], [220]], dtype=np.int16))
        segmenter.accept(np.array([[0], [0]], dtype=np.int16))
        self.assertFalse(segmenter.should_stop())

        segmenter.accept(np.array([[0], [0], [0], [0]], dtype=np.int16))

        self.assertTrue(segmenter.should_stop())


if __name__ == "__main__":
    unittest.main()
