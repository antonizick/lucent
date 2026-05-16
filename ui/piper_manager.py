import io
import json
import re
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

from piper import PiperVoice
from piper.config import SynthesisConfig


def sanitize_for_tts(text: str) -> str:
    """Remove markdown and special formatting characters for cleaner TTS output."""
    # Remove markdown bold/italic: **text** → text, *text* → text, __text__ → text
    text = re.sub(r'[\*_]{1,2}', '', text)
    # Remove markdown headers: # → nothing (including multi-level like ###)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    # Remove inline header markers that don't have leading space: "### heading" → "heading"
    text = re.sub(r'\s+#+\s+', ' ', text)
    # Remove markdown strikethrough: ~~text~~ → text
    text = re.sub(r'~~', '', text)
    # Remove markdown inline code: `text` → text
    text = re.sub(r'`', '', text)
    # Remove markdown links: [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove markdown blockquotes: > → nothing
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    # Remove markdown list markers: - → nothing, * → nothing
    text = re.sub(r'^[\-\*]\s+', '', text, flags=re.MULTILINE)
    # Remove markdown numbered lists: 1. → nothing
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    # Remove markdown horizontal rules: --- → nothing, *** → nothing
    text = re.sub(r'^[-_*]{3,}$', '', text, flags=re.MULTILINE)
    # Clean up any multiple spaces that may have resulted
    text = re.sub(r'  +', ' ', text)
    return text


@dataclass
class VoiceInfo:
    name: str
    language: str
    quality: str
    gender: str
    sample_rate: int


class PiperManager:
    """
    Manages Piper TTS lifecycle: model loading, synthesis, voice switching.
    Thread-safe via a single lock guarding all model access.
    """

    def __init__(self, voices_dir: str | Path):
        self._voices_dir = Path(voices_dir)
        if not self._voices_dir.exists():
            raise FileNotFoundError(
                f"Voices directory not found: {voices_dir}\n"
                "Run: bash setup.sh"
            )
        self._model_lock = threading.Lock()
        self._voice: PiperVoice | None = None
        self._current_name: str | None = None
        self._speed: float = 1.0  # length_scale: < 1 faster, > 1 slower
        self._stats: dict = {
            "synthesis_count": 0,
            "total_audio_seconds": 0.0,
            "mean_synthesis_ms": 0.0,
            "uptime_start": time.time(),
        }

    def load_voice(self, name: str) -> bool:
        """Load a voice model by name (without extension). Thread-safe."""
        onnx_path = self._voices_dir / f"{name}.onnx"
        config_path = self._voices_dir / f"{name}.onnx.json"

        if not onnx_path.exists() or not config_path.exists():
            return False

        with self._model_lock:
            try:
                self._voice = PiperVoice.load(str(onnx_path))
                self._current_name = name
                return True
            except Exception:
                self._voice = None
                self._current_name = None
                return False

    def synthesize_wav(self, text: str) -> bytes:
        """
        Synthesize text to a complete WAV file in memory.
        Synchronous — call via run_in_executor in async context.
        Thread-safe — holds lock for the duration of synthesis.
        """
        with self._model_lock:
            if not self._voice:
                raise RuntimeError("No voice loaded")

            start = time.monotonic()
            syn_config = SynthesisConfig(length_scale=self._speed) if self._speed != 1.0 else None
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file, syn_config=syn_config)
            elapsed_ms = (time.monotonic() - start) * 1000
            wav_bytes = wav_io.getvalue()

            # Update statistics
            self._stats["synthesis_count"] += 1
            n = self._stats["synthesis_count"]
            self._stats["mean_synthesis_ms"] = (
                (self._stats["mean_synthesis_ms"] * (n - 1) + elapsed_ms) / n
            )
            # Estimate audio duration from WAV size (16-bit mono)
            sample_rate = self.sample_rate
            if sample_rate:
                audio_seconds = (len(wav_bytes) - 44) / (sample_rate * 2)
                self._stats["total_audio_seconds"] += max(0, audio_seconds)

            return wav_bytes

    def list_available(self) -> list[VoiceInfo]:
        """Scan voices_dir for .onnx files and return metadata."""
        voices = []
        for onnx_path in sorted(self._voices_dir.glob("*.onnx")):
            config_path = onnx_path.with_suffix(".onnx.json")
            name = onnx_path.stem

            sample_rate = 22050
            language = "en"
            quality = "medium"
            gender = "unknown"

            if config_path.exists():
                try:
                    cfg = json.loads(config_path.read_text())
                    sample_rate = cfg.get("audio", {}).get("sample_rate", 22050)
                    language = cfg.get("language", {}).get("code", "en")
                    # Parse quality and gender from name convention
                    parts = name.split("-")
                    quality = parts[-1] if parts[-1] in ("low", "medium", "high") else "medium"
                    if "female" in name or "jenny" in name or "cori" in name or "alba" in name:
                        gender = "female"
                    elif "male" in name or "alan" in name or "northern" in name:
                        gender = "male"
                    else:
                        gender = "unknown"
                except Exception:
                    pass

            voices.append(VoiceInfo(
                name=name,
                language=language,
                quality=quality,
                gender=gender,
                sample_rate=sample_rate,
            ))
        return voices

    def unload(self) -> None:
        """Unload the current voice model and free memory."""
        with self._model_lock:
            self._voice = None
            self._current_name = None

    @property
    def sample_rate(self) -> int:
        if not self._voice:
            return 22050
        try:
            return self._voice.config.sample_rate
        except Exception:
            return 22050

    @property
    def is_loaded(self) -> bool:
        return self._voice is not None

    @property
    def current_name(self) -> str | None:
        return self._current_name

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = max(0.25, min(4.0, float(value)))

    def get_stats(self) -> dict:
        return {
            "voice": self._current_name,
            "sample_rate": self.sample_rate,
            "loaded": self.is_loaded,
            "speed": self._speed,
            "synthesis_count": self._stats["synthesis_count"],
            "total_audio_seconds": round(self._stats["total_audio_seconds"], 1),
            "mean_synthesis_ms": round(self._stats["mean_synthesis_ms"], 0),
            "uptime_seconds": round(time.time() - self._stats["uptime_start"], 0),
        }
