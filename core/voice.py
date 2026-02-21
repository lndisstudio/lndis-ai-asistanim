"""
Voice Engine — Speech-to-Text (STT) and Text-to-Speech (TTS)

Uses:
  TTS: pyttsx3 (offline, Windows SAPI5 — no API key needed)
  STT: SpeechRecognition + PyAudio (Google Speech API or offline)
"""

from __future__ import annotations

import threading
import queue
from typing import Callable


class VoiceEngine:
    """Handles voice input (mic → text) and voice output (text → speech)."""

    def __init__(self):
        self._tts_engine = None
        self._tts_lock = threading.Lock()
        self._tts_ready = False
        self._recognizer = None
        self._mic_available = False
        self._speaking = False
        self._tts_queue: queue.Queue[str] = queue.Queue()

        # TTS settings
        self.tts_enabled = True
        self.tts_rate = 175       # words per minute
        self.tts_volume = 0.9     # 0.0 - 1.0
        self.voice_index = 0      # 0 = default voice

        # STT settings
        self.stt_language = "tr-TR"  # Turkish default
        self.stt_timeout = 5         # seconds to wait for speech
        self.stt_phrase_limit = 15   # max seconds per phrase

        self._init_stt()

        # Start TTS worker thread (initializes engine inside)
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    # ── TTS (Text-to-Speech) ──────────────────────────────────

    def _tts_worker(self):
        """Background thread that processes TTS queue."""
        # Initialize engine inside the thread for COM stability on Windows
        try:
            import pyttsx3
            # We must use a local variable here to avoid threading issues during init
            engine = pyttsx3.init()
            engine.setProperty('rate', self.tts_rate)
            engine.setProperty('volume', self.tts_volume)
            
            voices = engine.getProperty('voices')
            self._voices = voices
            for i, v in enumerate(voices):
                if 'turkish' in v.name.lower() or 'tr' in (v.id or '').lower():
                    self.voice_index = i
                    engine.setProperty('voice', v.id)
                    break
            
            self._tts_engine = engine
            self._tts_ready = True
        except Exception as e:
            print(f"[Voice] TTS init failed in thread: {e}")
            self._tts_ready = False

        while True:
            text = self._tts_queue.get()
            if text is None:
                break
            
            if self._tts_ready and self.tts_enabled:
                with self._tts_lock:
                    try:
                        self._speaking = True
                        self._tts_engine.say(text)
                        self._tts_engine.runAndWait()
                    except Exception as e:
                        print(f"[Voice] TTS runtime error: {e}")
                    finally:
                        self._speaking = False
            
            self._tts_queue.task_done()

    def speak(self, text: str):
        """Queue text to be spoken (strictly sequential)."""
        if self.tts_enabled:
            # Clean text (remove markdown symbols that sound weird)
            clean_text = text.replace("*", "").replace("#", "").replace("`", "").replace("_", "")
            self._tts_queue.put(clean_text)

    def stop_speaking(self):
        """Stop current speech."""
        if self._tts_ready:
            try:
                with self._tts_lock:
                    self._tts_engine.stop()
            except Exception:
                pass

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def list_voices(self) -> list[dict]:
        """Return available system voices."""
        if not self._tts_ready:
            return []
        return [
            {"index": i, "name": v.name, "id": v.id, "lang": getattr(v, 'languages', [])}
            for i, v in enumerate(self._voices)
        ]

    def set_voice(self, index: int):
        """Set voice by index."""
        if self._tts_ready and 0 <= index < len(self._voices):
            self.voice_index = index
            self._tts_engine.setProperty('voice', self._voices[index].id)

    def set_rate(self, rate: int):
        """Set speech rate (words per minute)."""
        self.tts_rate = rate
        if self._tts_ready:
            self._tts_engine.setProperty('rate', rate)

    # ── STT (Speech-to-Text) ──────────────────────────────────

    def _init_stt(self):
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = 300
            self._recognizer.dynamic_energy_threshold = True

            # Check microphone availability
            try:
                sr.Microphone()
                self._mic_available = True
            except (OSError, AttributeError):
                self._mic_available = False
        except ImportError:
            self._recognizer = None
            self._mic_available = False

    @property
    def mic_available(self) -> bool:
        return self._mic_available

    def listen(
        self,
        on_result: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_listening: Callable[[], None] | None = None,
    ) -> str | None:
        """
        Listen to microphone and return transcribed text.

        Callbacks (optional, for async UI updates):
          on_listening() — called when mic is active
          on_result(text) — called with transcription
          on_error(msg) — called on error
        """
        if not self._recognizer or not self._mic_available:
            msg = "Microphone not available"
            if on_error:
                on_error(msg)
            return None

        import speech_recognition as sr

        try:
            with sr.Microphone() as source:
                # Ambient noise adjustment
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)

                if on_listening:
                    on_listening()

                audio = self._recognizer.listen(
                    source,
                    timeout=self.stt_timeout,
                    phrase_time_limit=self.stt_phrase_limit,
                )

            # Try Google Speech Recognition (online)
            try:
                text = self._recognizer.recognize_google(audio, language=self.stt_language)
                if on_result:
                    on_result(text)
                return text
            except sr.UnknownValueError:
                msg = "Could not understand audio"
                if on_error:
                    on_error(msg)
                return None
            except sr.RequestError as e:
                msg = f"Speech recognition service error: {e}"
                if on_error:
                    on_error(msg)
                return None

        except sr.WaitTimeoutError:
            msg = "No speech detected"
            if on_error:
                on_error(msg)
            return None
        except Exception as e:
            msg = f"Microphone error: {e}"
            if on_error:
                on_error(msg)
            return None

    def listen_async(
        self,
        on_result: Callable[[str], None],
        on_error: Callable[[str], None] | None = None,
        on_listening: Callable[[], None] | None = None,
    ):
        """Listen in background thread."""
        threading.Thread(
            target=self.listen,
            args=(on_result, on_error, on_listening),
            daemon=True,
        ).start()

    # ── Status ─────────────────────────────────────────────────

    @property
    def status(self) -> dict:
        return {
            "tts_ready": self._tts_ready,
            "tts_enabled": self.tts_enabled,
            "mic_available": self._mic_available,
            "stt_language": self.stt_language,
            "voice_count": len(self._voices) if self._tts_ready else 0,
            "speaking": self._speaking,
        }
