# NX Vox — Piper TTS Integration Plan

**Status:** Draft for review  
**Version:** 1.1  
**Date:** 2026-05-14  
**Author:** Lucent  
**License:** GPL-3.0 (plan content)  

---

## Executive Summary

NX Vox replaces the browser-side Web Speech API (espeak-ng on Linux, Microsoft SAPI on Windows) with server-side neural TTS via [Piper](https://github.com/OHF-Voice/piper1-gpl). The result is a natural, consistent voice that sounds identical regardless of browser or operating system, with no cloud dependencies and zero recurring cost.

**Key decisions:**
- **Engine:** Piper TTS (OHF-Voice fork, v1.4.2, GPL-3.0)
- **Integration:** In-process Python library — no new services
- **Voice:** `en_GB-southern_english_female-medium` (~35MB, ~1x real-time on CPU)
- **Audio delivery:** Base64 WAV over existing SSE streaming pipeline
- **Audio interruption:** Cancel-on-new — new utterance stops any currently playing audio
- **Fallback:** Graceful degradation to browser `window.speechSynthesis`
- **Estimated effort:** 6-8 hours

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Piper TTS — Research Summary](#2-piper-tts--research-summary)
3. [Architecture — Detailed Design](#3-architecture--detailed-design)
4. [API Specification](#4-api-specification)
5. [Frontend Changes](#5-frontend-changes)
6. [Implementation Plan](#6-implementation-plan)
7. [Testing Strategy](#7-testing-strategy)
8. [Drawbacks & Concerns](#8-drawbacks--concerns)
9. [Alternatives Considered](#9-alternatives-considered)
10. [Edge Cases & Failure Modes](#10-edge-cases--failure-modes)
11. [Rollout Strategy](#11-rollout-strategy)
12. [Security Considerations](#12-security-considerations)
13. [Glossary](#13-glossary)
14. [How to Provide Feedback](#14-how-to-provide-feedback)
15. [Appendix A: Reference Implementations](#15-appendix-a-reference-implementations)

---

## 1. Problem Statement

### 1.1 Current Architecture

```
┌─────────────────────────────────────────────┐
│ Browser (Frontend)                          │
│                                             │
│  SSE /speak/stream ← text → speakText()     │
│                         ↓                   │
│              window.speechSynthesis          │
│               (platform-native TTS)         │
│                                             │
│  Linux:           espeak-ng (robotic)       │
│  Windows:         Microsoft SAPI            │
│  macOS:           NSSpeechSynthesizer       │
└─────────────────────────────────────────────┘
```

### 1.2 Identified Problems

| # | Problem | Impact |
|---|---------|--------|
| 1 | **Voice quality is OS-dependent** | Linux users hear robotic espeak-ng; Windows users hear something entirely different. The experience varies wildly by platform. |
| 2 | **No voice consistency** | The assistant sounds different on every browser/OS combination. Brand consistency is impossible. |
| 3 | **Limited control** | Web Speech API offers no per-utterance speed/pitch tuning, no SSML support, no audio format control, no prosody adjustment. |
| 4 | **No offline capability** | Synthesis happens inside the browser — you cannot cache, post-process, or archive generated audio. |
| 5 | **No multi-client consistency** | Each browser tab has its own synthesis context. Voices drift across tabs and sessions. |
| 6 | **No extensibility** | Adding custom voices, emotion modeling, or voice switching requires replacing the entire mechanism. |

### 1.3 Target Architecture

```
┌───────────────────────────────────────────────────┐
│ Server (Python/FastAPI, port 8001)                │
│                                                    │
│  POST /speak                                       │
│       │                                            │
│       ▼                                            │
│  PiperManager.synthesize("text")                   │
│       │                                            │
│       ├─▸ PiperVoice.synthesize_wav() → WAV bytes  │
│       │                                            │
│       ▼                                            │
│  base64 encode → SSE broadcast                     │
│       │                                            │
│       ▼                                            │
│  SSE: { text, audio (base64), format, sample_rate } │
│                                                    │
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────┐
│ Browser (Frontend)                                │
│                                                    │
│  EventSource /speak/stream                         │
│       │                                            │
│       ▼                                            │
│  parse JSON → decode base64 → ArrayBuffer          │
│       │                                            │
│       ▼                                            │
│  AudioContext.decodeAudioData() → AudioBuffer      │
│       │                                            │
│       ▼                                            │
│  AudioBufferSourceNode.start() → you hear voice    │
└───────────────────────────────────────────────────┘
```

---

## 2. Piper TTS — Research Summary

### 2.1 Engine Overview

| Attribute | Value |
|-----------|-------|
| **Project** | [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) |
| **Status** | Active — v1.4.2 (April 2026), maintained by Open Home Foundation |
| **License** | GPL-3.0 |
| **Model architecture** | VITS (Conditional Variational Autoencoder + Adversarial Training) |
| **Inference runtime** | ONNX Runtime (CPU, CUDA, DirectML) |
| **Install** | `pip install piper-tts` — pre-built wheels available for Linux, macOS, Windows |
| **Languages** | 40+ languages (Arabic through Chinese — see VOICES.md) |
| **Voice sizes** | Low (~10MB) / Medium (~30-50MB) / High (~100-200MB) per voice |
| **Speed (medium model)** | ~1× real-time on modern x86 CPU; ~3-4× on CUDA GPU |
| **Startup latency** | ~2-4 seconds to load a medium model at server startup |
| **Python API** | `PiperVoice.load()`, `.synthesize_wav()`, `.synthesize()` (streaming) |
| **Built-in HTTP server** | Flask-based on port 5000 (`python3 -m piper.http_server`) |
| **Synthesis controls** | `volume`, `length_scale` (speed), `noise_scale` (variation), `noise_w_scale` |
| **Audio output** | WAV (int16 PCM), raw PCM chunks, or direct file write |
| **Phoneme injection** | `[[ bˈætmæn ]]` syntax for raw espeak-ng phoneme overrides |
| **Used by** | Home Assistant, NVDA (screen reader), OpenVoiceOS, LocalAI |

### 2.2 Why Piper Over Alternatives

Piper was selected over alternatives (see [§9 Alternatives Considered](#9-alternatives-considered)) for:
- **Quality-to-speed ratio:** Neural VITS quality at ~1× real-time on CPU
- **Voice selection:** 40+ languages, multiple voices per language, British English female specifically
- **Maintenance:** Active development by Open Home Foundation, v1.4.2 as of April 2026
- **Integration:** `pip install piper-tts` with pre-built wheels — no compilation needed on standard platforms
- **Proven deployment:** Used in production by Home Assistant (millions of users)
- **License:** GPL-3.0, compatible with project license

### 2.3 Available British English Voices

Sources: [Piper VOICES.md](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md), [HuggingFace models](https://huggingface.co/rhasspy/piper-voices)

| Voice ID | Gender | Quality | Model Size | Notes |
|----------|--------|---------|------------|-------|
| `en_GB-alan-low` | Male | Low | ~10MB | Fastest British male, lower naturalness |
| `en_GB-alan-medium` | Male | Medium | ~35MB | Good quality British male voice |
| `en_GB-southern_english_female-low` | Female | Low | ~10MB | Female, fast but robotic |
| `en_GB-southern_english_female-medium` | Female | Medium | ~35MB | **Recommended** — best quality female British |
| `en_GB-southern_english_male-medium` | Male | Medium | ~35MB | Solid male alternative |
| `en_GB-vctk-medium` | Mixed | Medium | ~40MB | Multi-speaker (multiple identities in one model) |

**Recommendation:** `en_GB-southern_english_female-medium`. VITS model trained on Southern British English accent. Natural prosody, good intonation, appropriate for an assistant voice.

### 2.4 Voice Model Licensing

Each voice model on HuggingFace includes a `MODEL_CARD` file with its specific license. Piper's voice models generally use permissive licenses (MIT-style, "RHASSY sounds-like"). Users should review the `MODEL_CARD` for their chosen voice before commercial deployment.

Voice model files are **not** distributed through PyPI — they are downloaded separately from HuggingFace via `python3 -m piper.download_voices <voice_id>`. A `setup.sh` script (see §6, Phase 1) automates this step so that new machines can reproduce the environment without manual steps.

---

## 3. Architecture — Detailed Design

### 3.1 System Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ Server Process (port 8001)                                       │
│                                                                  │
│  ┌─────────────────────────────────────────┐                     │
│  │ FastAPI (server.py)                      │                     │
│  │                                          │                     │
│  │  ┌─────────────────────────────────────┐ │                     │
│  │  │ PiperManager                        │ │                     │
│  │  │  ┌───────────────────────────────┐  │ │                     │
│  │  │  │ PiperVoice (piper-tts)        │  │ │                     │
│  │  │  │  .onnx model (loaded once)    │  │ │                     │
│  │  │  │  .onnx.json config            │  │ │                     │
│  │  │  └───────────────────────────────┘  │ │                     │
│  │  │  threading.Lock (_model_lock)        │ │                     │
│  │  │                                      │ │                     │
│  │  │  synthesize_text(text) → WAV bytes   │ │                     │
│  │  │  list_voices() → voice metadata      │ │                     │
│  │  │  switch_voice(name) → reload model   │ │                     │
│  │  └─────────────────────────────────────┘ │                     │
│  │                                          │                     │
│  │  Existing components:                    │                     │
│  │  ┌─────────────────────────────────────┐ │                     │
│  │  │ speech_queue     │ speech_event     │ │                     │
│  │  │ last_speech      │ SSE clients      │ │                     │
│  │  └─────────────────────────────────────┘ │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                  │
│  ┌─── API Endpoints ──────────────────────────────────────────┐  │
│  │  POST /speak      → synthesize + broadcast via SSE         │  │
│  │  GET  /speak/stream → SSE endpoint (modified for audio)    │  │
│  │  POST /vox/speak  → synthesize + return audio directly     │  │
│  │  GET  /vox/voices → list available voices                  │  │
│  │  POST /vox/voice  → switch active voice                    │  │
│  │  GET  /vox/status → current voice info + statistics        │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow — Full Synthesis Pipeline

```
Client                     Server                          Piper              Browser
  │                          │                               │                   │
  │  POST /speak             │                               │                   │
  │  { "text": "Hello" }     │                               │                   │
  │ ─────────────────────►   │                               │                   │
  │                          │  PiperManager.synthesize()    │                   │
  │                          │ ──────────────────────────►   │                   │
  │                          │                               │                   │
  │                          │  ◄── WAV bytes (22050Hz PCM) ─                   │
  │                          │                               │                   │
  │                          │  Encode to base64             │                   │
  │                          │  Build SSE event              │                   │
  │                          │                               │                   │
  │                          │  SSE /speak/stream             │                   │
  │  ◄─────────────────────  │  data: { text, audio,         │                   │
  │                          │         format, sample_rate }  │                   │
  │                          │                               │                   │
  │  Decode base64            │                               │                   │
  │  AudioContext.play()     │                               │                   │
  │ ───────────────────────────────────────────────────────────────────►        │
  │                          │                               │               (audio)
```

### 3.3 PiperManager Class Specification

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Generator
import threading

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

    Thread-safe: a threading.Lock guards all model access. Synthesis and
    voice switching cannot overlap — switch_voice() blocks until any
    in-progress synthesis completes, then reloads the model.
    """

    def __init__(self, voices_dir: str | Path):
        """
        Args:
            voices_dir: Directory containing .onnx and .onnx.json files.
                        Raises FileNotFoundError if the directory does not exist.
        """
        ...

    def load_voice(self, name: str) -> bool:
        """
        Load a voice model by name (without extension).

        Looks for {name}.onnx and {name}.onnx.json in voices_dir.
        Unloads previous model if one was loaded.
        Returns True on success, False if files not found or load fails.
        Thread-safe — acquires _model_lock.
        """
        ...

    def synthesize_wav(self, text: str) -> bytes:
        """
        Synthesize text to a complete WAV file in memory.

        Returns WAV bytes (int16 PCM, voice-specific sample rate).
        Synchronous — call via run_in_executor in async context.
        Thread-safe — acquires _model_lock for the duration of synthesis.
        Raises RuntimeError if no voice is loaded.
        """
        ...

    def list_available(self) -> list[VoiceInfo]:
        """
        Scan voices_dir for .onnx files and return metadata.

        Parses the companion .onnx.json config for sample_rate and language.
        Returns list of VoiceInfo(name, language, quality, gender, sample_rate).
        """
        ...

    def unload(self) -> None:
        """Unload the current voice model and free memory."""
        ...

    @property
    def sample_rate(self) -> int:
        """Sample rate of the currently loaded voice model."""
        ...

    @property
    def is_loaded(self) -> bool:
        """Whether a voice model is currently loaded."""
        ...
```

**Note:** `synthesize_stream()` is intentionally excluded from this interface. Streaming PCM delivery via SSE requires a more complex chunked protocol and is not needed for the initial implementation. It is documented as a future enhancement in §8.5 only.

### 3.4 Thread Safety

`PiperManager` uses a single `threading.Lock` (`_model_lock`) that is held for the duration of both `synthesize_wav()` and `load_voice()`. This ensures:

- Voice switching never races with an active synthesis job.
- `load_voice()` (called during a voice switch) waits for any in-progress `synthesize_wav()` to complete before unloading the model.
- Multiple rapid synthesis requests queue naturally via the `ThreadPoolExecutor` and the lock.

```python
class PiperManager:
    def __init__(self, voices_dir):
        self._model_lock = threading.Lock()
        self._voice: PiperVoice | None = None
        ...

    def synthesize_wav(self, text: str) -> bytes:
        with self._model_lock:
            if not self._voice:
                raise RuntimeError("No voice loaded")
            ...  # call self._voice.synthesize_wav(text)

    def load_voice(self, name: str) -> bool:
        with self._model_lock:
            ...  # unload existing, load new
```

### 3.5 Async Wrapping

Piper's synthesis is synchronous and CPU-bound. In the async FastAPI server, synthesis must run in a thread pool executor to avoid blocking the event loop:

```python
from concurrent.futures import ThreadPoolExecutor
import asyncio

piper_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="piper")
piper = PiperManager("ui/voices")

async def synthesize_async(text: str) -> bytes:
    """Synthesis wrapper that doesn't block the event loop."""
    loop = asyncio.get_running_loop()  # not get_event_loop() — deprecated in 3.10+
    return await loop.run_in_executor(
        piper_executor, piper.synthesize_wav, text
    )
```

`max_workers=1` prevents multiple synthesis jobs from competing for CPU/GPU. Multiple rapid requests queue naturally via the executor. The lock inside `PiperManager` provides the second line of defense.

### 3.6 FastAPI Lifespan

Server startup uses the modern FastAPI `lifespan` context manager, not the deprecated `@app.on_event("startup")` pattern:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load Piper voice model (~2-4 seconds for medium model)
    piper.load_voice("en_GB-southern_english_female-medium")
    init_logs_dirs()
    yield
    # Shutdown: free model memory
    piper.unload()

app = FastAPI(lifespan=lifespan)
```

**Note:** The model load during startup adds ~2-4 seconds to the server's startup time. The systemd unit's `ExecStartPost` healthcheck (or equivalent readiness probe) must account for this. The `/services/health` endpoint should not return `200 OK` until `piper.is_loaded` is `True`.

---

## 4. API Specification

### 4.1 Modified — POST /speak

**Request** (unchanged):
```json
{
  "text": "Hello, this is a test."
}
```

**Response** (new audio fields added):
```json
{
  "status": "queued",
  "text": "Hello, this is a test.",
  "audio": "//uZxAAAAA...base64-encoded-wav...",
  "format": "audio/wav",
  "sample_rate": 22050,
  "timestamp": "2026-05-14T00:50:00.000000"
}
```

The `audio` field contains the complete WAV file as a base64-encoded string. `format` indicates the audio encoding. `sample_rate` lets the browser configure the AudioContext correctly.

**Backward compatibility:** Clients that ignore unknown JSON fields continue to work; they simply use `text` as before. Clients that check for `audio` use the new pipeline.

### 4.2 Modified — SSE /speak/stream

**Event format (before):**
```
data: { "text": "Hello", "timestamp": "..." }
```

**Event format (after):**
```
data: { "text": "Hello", "audio": "//uZx...", "format": "audio/wav", "sample_rate": 22050, "timestamp": "..." }
```

The `audio` field is optional. If present, the frontend should use audio playback. If absent, fall back to browser TTS (backward compatibility for mixed environments during migration).

**SSE payload size note:** A 5-second utterance produces ~293KB of base64-encoded audio per SSE message. The native browser `EventSource` API handles this without issue. Third-party SSE polyfills or proxies may have message size limits — verify compatibility before introducing either. Gzip at the HTTP layer reduces this by ~40-60%.

### 4.3 New — GET /vox/voices

Returns all available voices and the currently active one.

```json
{
  "voices": [
    {
      "name": "en_GB-southern_english_female-medium",
      "language": "en_GB",
      "quality": "medium",
      "gender": "female",
      "sample_rate": 22050
    },
    {
      "name": "en_GB-alan-medium",
      "language": "en_GB",
      "quality": "medium",
      "gender": "male",
      "sample_rate": 22050
    }
  ],
  "current": "en_GB-southern_english_female-medium"
}
```

### 4.4 New — POST /vox/voice

Switch the active voice model. Blocks until any in-progress synthesis completes, then reloads (~1-2 seconds for model swap after lock acquisition).

**Request:**
```json
{
  "voice": "en_GB-alan-medium"
}
```

**Response:**
```json
{
  "status": "switched",
  "voice": "en_GB-alan-medium",
  "previous": "en_GB-southern_english_female-medium",
  "duration_ms": 1450
}
```

### 4.5 New — GET /vox/status

Runtime status of the Piper subsystem.

```json
{
  "voice": "en_GB-southern_english_female-medium",
  "sample_rate": 22050,
  "loaded": true,
  "synthesis_count": 42,
  "total_audio_seconds": 84.5,
  "mean_synthesis_ms": 1120,
  "uptime_seconds": 8040
}
```

### 4.6 New — POST /vox/speak

Direct synthesis endpoint — returns audio without broadcasting via SSE. Useful for programmatic callers (Discord bot, API consumers).

**Request:**
```json
{
  "text": "Hello world"
}
```

**Response:**
Binary WAV audio (`Content-Type: audio/wav`). Accept: `application/json` returns the same base64 JSON response as POST /speak.

---

## 5. Frontend Changes

### 5.1 New Audio Playback Module

```javascript
// audio-player.js — Server-side TTS audio playback

let audioContext = null;
let currentSource = null;  // Track playing source for cancel-on-new

function ensureAudioContext() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioContext;
}

async function playAudioFromBase64(base64Audio) {
    const ctx = ensureAudioContext();

    // Browsers require user gesture before AudioContext can play
    if (ctx.state === 'suspended') {
        await ctx.resume();
    }

    // Cancel any currently playing audio (cancel-on-new policy)
    if (currentSource) {
        currentSource.onended = null;  // Prevent stale onended callback
        currentSource.stop();
        currentSource = null;
    }

    // Decode base64 to binary
    const binaryStr = atob(base64Audio);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
    }

    // Decode WAV to AudioBuffer (browser handles WAV parsing)
    const audioBuffer = await ctx.decodeAudioData(bytes.buffer);

    // Create and play source node
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    source.start(0);
    currentSource = source;

    return source; // Return for lifecycle management (stop, events, etc.)
}

function speakFallback(text) {
    // Original browser TTS as fallback
    const utterance = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterance);
}
```

### 5.2 Modified SSE Handler

```javascript
// Before: only handled text
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    speakText(data.text);
    displayText(data.text);
};

// After: prefers server-side audio, falls back to browser TTS
eventSource.onmessage = async (event) => {
    const data = JSON.parse(event.data);
    displayText(data.text);

    if (data.audio) {
        try {
            startSpeakingAnimation();
            const source = await playAudioFromBase64(data.audio);
            source.onended = () => stopSpeakingAnimation();
        } catch (err) {
            console.error("Audio playback failed:", err);
            stopSpeakingAnimation();
            // Degrade to browser TTS on any audio error
            if (window.speechSynthesis) speakFallback(data.text);
        }
    } else if (window.speechSynthesis) {
        speakText(data.text);
    }
};
```

**Note:** `startSpeakingAnimation()` is called immediately on event receipt. `stopSpeakingAnimation()` is attached to `source.onended` — this fires when the AudioBufferSourceNode finishes playing, keeping animation duration accurate. The `try/finally` structure ensures `stopSpeakingAnimation()` is always called even if playback throws.

### 5.3 Voice Selection UI

The existing voice dropdown should be populated from `GET /vox/voices` instead of `window.speechSynthesis.getVoices()`. The first option should match the server's current voice.

### 5.4 Visual Synchronization

The existing speaking animation (avatar mouth movement, glow effect) is controlled by `startSpeakingAnimation()` / `stopSpeakingAnimation()`. These work correctly with the audio pipeline — start on SSE event receipt, stop when `AudioBufferSourceNode` fires its `onended` event.

For optional audio visualization, connect an `AnalyserNode` between the source and destination:

```javascript
const analyser = ctx.createAnalyser();
source.connect(analyser);
analyser.connect(ctx.destination);
// analyser.frequencyBinCount → visualization data
```

---

## 6. Implementation Plan

### Phase 0 — Environment Setup (30 min)

A `setup.sh` script in the project root handles all environment setup. This ensures new machines can reproduce the environment without manual steps.

```bash
#!/usr/bin/env bash
# setup.sh — NX Vox environment setup
set -e

echo "=== Installing Piper TTS ==="
pip install piper-tts

echo "=== Verifying Piper CLI ==="
python3 -m piper --help > /dev/null && echo "Piper CLI OK"

echo "=== Downloading voice model ==="
VOICE="en_GB-southern_english_female-medium"
VOICES_DIR="ui/voices"
mkdir -p "$VOICES_DIR"

if [ ! -f "$VOICES_DIR/${VOICE}.onnx" ]; then
    python3 -m piper.download_voices "$VOICE"
    mv ~/.local/share/piper/${VOICE}* "$VOICES_DIR/"
    echo "Voice model downloaded to $VOICES_DIR/"
else
    echo "Voice model already present — skipping download"
fi

echo "=== Verifying synthesis ==="
python3 -m piper \
    -m "$VOICES_DIR/$VOICE" \
    -f /tmp/piper-test.wav \
    -- "Setup verification complete."
echo "Synthesis OK — test audio at /tmp/piper-test.wav"
```

Run: `bash setup.sh` once on a new machine. Subsequent runs are idempotent.

### Phase 1 — Backend: PiperManager (2 hours)

1. **Create `ui/piper_manager.py`:**
   - Implement `PiperManager` with `VoiceInfo` dataclass as specified in §3.3
   - `_model_lock = threading.Lock()` guards all model access
   - `load_voice()` acquires lock, checks for `.onnx` and `.onnx.json`, loads model
   - `synthesize_wav()` acquires lock, raises `RuntimeError` if `not is_loaded`
   - `list_available()` scans `voices_dir` for `.onnx` files, parses companion `.onnx.json` for metadata
   - `unload()` acquires lock, sets `_voice = None`

2. **Add startup-time model check to `PiperManager.__init__()`:**
   ```python
   def __init__(self, voices_dir: str | Path):
       self._voices_dir = Path(voices_dir)
       if not self._voices_dir.exists():
           raise FileNotFoundError(
               f"Voices directory not found: {voices_dir}\n"
               f"Run: bash setup.sh"
           )
       self._model_lock = threading.Lock()
       self._voice = None
       self._stats = {"synthesis_count": 0, "total_audio_seconds": 0.0, ...}
   ```

3. **Wire into `ui/server.py`** using the `lifespan` pattern from §3.6:
   ```python
   from piper_manager import PiperManager, synthesize_async

   piper = PiperManager(Path(__file__).parent / "voices")

   @asynccontextmanager
   async def lifespan(app: FastAPI):
       piper.load_voice("en_GB-southern_english_female-medium")
       init_logs_dirs()
       yield
       piper.unload()

   app = FastAPI(lifespan=lifespan)
   ```

4. **Update `/services/health` to reflect Piper readiness:**
   ```python
   @app.get("/services/health")
   async def health():
       return {
           "Voice box": "running",
           "piper": "ready" if piper.is_loaded else "loading"
       }
   ```
   The healthcheck script in CLAUDE.md (`grep -q "Voice box"`) continues to work unchanged.

### Phase 2 — Backend: API Endpoints (1 hour)

5. **Modify POST /speak:**
   - After queuing text, call `synthesize_async(text)` inside a `try/except`
   - On success: base64-encode WAV bytes, include `audio`, `format`, `sample_rate` in response and SSE broadcast
   - On failure: log exception, continue without `audio` field (fallback path)

6. **Modify SSE /speak/stream:**
   - Broadcast events now include `audio` field (base64 string) when Piper is loaded
   - Keep `text` field for backward-compatible parsers

7. **Add NEW endpoints:**
   - `GET /vox/voices` — delegate to `piper.list_available()`
   - `POST /vox/voice` — call `piper.load_voice()` in executor (blocks while synthesis completes via lock)
   - `GET /vox/status` — return runtime statistics from `piper._stats`
   - `POST /vox/speak` — synthesize and return raw WAV (`Content-Type: audio/wav`)

### Phase 3 — Frontend: Audio Playback (1 hour)

8. **Add `ui/static/audio-player.js`:**
   - `playAudioFromBase64()` with `currentSource` tracking (cancel-on-new) as specified in §5.1
   - `ensureAudioContext()` with autoplay policy handling

9. **Modify SSE handler in `ui/static/app.js`:**
   - Wrap playback in `try/catch` with `stopSpeakingAnimation()` in error path
   - Attach `stopSpeakingAnimation()` to `source.onended`
   - Detect `data.audio` → use server-side audio; absent → `speakText()` fallback

10. **Wire voice selector to `/vox/voices`:**
    - Populate dropdown from API response
    - `POST /vox/voice` on selection change

### Phase 4 — Polish & Error Handling (1 hour)

11. **Graceful degradation chain:**
    ```
    Piper loads ✓     → server-side TTS
    Piper fails ✗     → POST /speak omits audio → frontend uses browser TTS
    Browser no AudioContext → SpeechSynthesis fallback
    AudioContext throws → catch, stopSpeakingAnimation(), SpeechSynthesis fallback
    ```

12. **Add `ui/voices/.gitignore`:**
    ```
    *.onnx
    *.onnx.json
    ```
    Model files are large (~35MB) and available on HuggingFace — don't commit.

13. **Systemd readiness window:**
    - `lucent-voice-box.service` startup now takes ~2-4 seconds longer (Piper model load)
    - Add `TimeoutStartSec=30` to the unit file if not already present
    - Ensure `ExecStartPost` healthcheck (if any) polls until `/services/health` returns `"piper": "ready"`

14. **Audio normalization (polish):**
    - Piper's `volume` parameter defaults to 1.0. Different voices and text lengths produce varying perceived loudness.
    - After synthesis, normalize WAV output to a target peak of -3 dBFS using Python's `audioop.max()` and a scaling pass.
    - This is a polish step — implement only after verifying loudness inconsistency is noticeable in practice.

### Effort Summary

| Phase | Tasks | Estimated Time |
|-------|-------|---------------|
| 0 — Environment | setup.sh, verify CLI, download model | 30 min |
| 1 — PiperManager | Class + thread safety + lifespan wiring | 2 hr |
| 2 — API Endpoints | Modify + new endpoints | 1 hr |
| 3 — Frontend | Audio playback, SSE handler, voice selector | 1 hr |
| 4 — Polish | Error handling, normalization, systemd, gitignore | 1 hr |
| **Total** | | **~5.5 hours** |

*Add 1-2 hours for debugging and integration surprises. Budget 6-8 hours for a production-quality result.*

---

## 7. Testing Strategy

### 7.1 Unit Tests

| Test | What It Validates |
|------|-------------------|
| `PiperManager.load_voice()` loads a valid model | No exceptions, `.is_loaded == True`, `.sample_rate > 0` |
| `PiperManager.synthesize_wav()` returns valid WAV | Output parses via `wave.open()`, correct sample rate, non-empty |
| `PiperManager.list_available()` returns voices | Correct count, expected voice names present, `VoiceInfo` fields populated |
| `PiperManager.unload()` frees resources | `.is_loaded == False`, subsequent `synthesize_wav()` raises `RuntimeError` |
| `PiperManager.load_voice()` with bad path returns False | Graceful failure, `.is_loaded == False` |
| Async wrapper `synthesize_async()` | Returns WAV bytes, uses `get_running_loop()` without deprecation warning |
| Concurrent synthesize + load_voice | Lock prevents race — one completes fully before the other starts |

### 7.2 Integration Tests

| Test | What It Validates |
|------|-------------------|
| `POST /speak` with Piper loaded | Returns 200, response has `audio`, `format`, `sample_rate` fields |
| `POST /speak` empty text | Returns 400 (unchanged behavior) |
| `POST /speak` without Piper | Returns 200, response omits `audio` field (fallback) |
| `GET /vox/voices` | Returns voice list with `current` field matching loaded voice |
| `POST /vox/voice` valid | Returns `status: "switched"`, subsequent `/speak` uses new voice |
| `POST /vox/voice` invalid | Returns 404, voice unchanged |
| `GET /vox/status` | Returns all fields, correct `synthesis_count` |
| `POST /vox/speak` JSON accept | Returns base64 JSON (identical to POST /speak) |
| `POST /vox/speak` binary accept | Returns `Content-Type: audio/wav`, valid WAV |
| `/services/health` before Piper loads | Returns `"piper": "loading"` |
| `/services/health` after Piper loads | Returns `"piper": "ready"` |

### 7.3 Browser Tests

| Test | What It Validates |
|------|-------------------|
| SSE delivers audio event | EventSource receives event with `audio` field |
| Audio plays through speakers | `playAudioFromBase64()` plays without errors |
| Fallback to browser TTS | When `audio` field absent, `speakText()` is called |
| AudioContext autoplay | Resumes on user click, does not block on first audio |
| Voice switching | Dropdown changes trigger voice switch, next audio uses new voice |
| Cancel-on-new | Second utterance arriving during playback cancels first, plays second |
| Animation lifecycle | `startSpeakingAnimation()` fires on event, `stopSpeakingAnimation()` fires on `onended` |
| Playback error path | Forced error calls `stopSpeakingAnimation()` and triggers `speakFallback()` |

### 7.4 Performance Tests

| Test | What It Validates |
|------|-------------------|
| Synthesis latency | Measure wall-clock time for N utterances of varying length |
| SSE payload timing | Time from POST to SSE event receipt |
| Memory steady-state | RSS before/after 100 synthesis calls (no leak) |
| Concurrent requests | Queue 5 simultaneous requests, confirm sequential processing |
| Startup latency | Time from `lifespan` start to `piper.is_loaded == True` |

---

## 8. Drawbacks & Concerns

### 8.1 GPL-3.0 License Compatibility

**Risk:** Piper is GPL-3.0. The voice models use permissive licenses (MIT-style / RHASSY sounds-like).

**Impact:** Compatible with GPL-licensed projects. If the host project's license changes to a non-GPL-compatible license (e.g., Apache 2.0, proprietary), Piper would need to be replaced or run as a separate process.

**Mitigation:** Current project license is GPL — no action required. Document this dependency for future license reviews.

### 8.2 Memory Usage

**Risk:** A medium voice model (~35MB on disk) loads into ~150-250MB RSS (model weights + ONNX Runtime session).

**Impact:** The server.py process grows by ~200MB. On a system with 8GB+ RAM this is negligible. On constrained hardware (Raspberry Pi, low-end VPS), this could be significant.

**Mitigation:**
- Acceptable for typical server hardware (2-4GB+ available)
- Monitor with `lucent-monitor` or `psutil`
- Low-quality voices (~10MB, ~50MB RSS) available as a fallback for constrained systems

### 8.3 CPU Load

**Risk:** Inference runs at approximately real-time speed on CPU. A 5-second utterance consumes ~5 seconds of CPU time.

**Impact:** Under sustained load, synthesis requests queue behind each other. On an idle system the user won't notice. On a busy system, responses may feel delayed.

**Mitigation:**
- Synthesis runs in `run_in_executor` — never blocks the event loop
- `ThreadPoolExecutor(max_workers=1)` prevents CPU thrashing
- CUDA acceleration available if an NVIDIA GPU is present (`use_cuda=True`)
- Browser TTS fallback remains as an escape hatch

### 8.4 Browser Autoplay Policy

**Risk:** Modern browsers block `AudioContext` from playing without a user gesture. On first page load, audio will not play until the user clicks somewhere.

**Impact:** First utterance of a session is visual-only (avatar animates, text appears, no sound).

**Mitigation:**
- Already handled by existing `speechEnabled` flag requiring first click
- `AudioContext.resume()` re-acquires playback permission on each interaction
- Show "Click to enable audio" indicator when context is suspended

### 8.5 SSE Payload Size

**Risk:** A 5-second utterance at 22050Hz, 16-bit mono = ~220KB raw WAV. Base64 encoding adds ~33% → ~293KB per SSE message.

**Impact:** Each SSE event carries ~300KB of data. For localhost communication this is fast. The native browser `EventSource` API handles messages of this size without issue. Third-party SSE polyfills or HTTP proxies may have smaller message size limits.

**Mitigation:**
- Acceptable for localhost and LAN (sub-millisecond transfer)
- Do not introduce SSE polyfills or proxies without verifying their message size limits
- Future optimization: deliver audio as a chunked HTTP response to `/vox/speak` rather than via SSE
- Gzip compression can reduce WAV data by ~40-60% (enable at HTTP level)

### 8.6 Voice Model Maintenance

**Risk:** Piper is looking for maintainers (per the project README). If development stops, no new voices or features land.

**Impact:** Existing models continue working indefinitely — ONNX is a stable format with no runtime dependency on the Piper project itself.

**Mitigation:** Model files are self-contained. They do not phone home. They do not require API access. If Piper stops development today, the current models will still work in 10 years. This is a risk for *future improvement*, not for current functionality.

### 8.7 Single Voice at a Time

**Risk:** In-process mode loads one model at a time (~35MB). Switching voices triggers a full model reload (~1-2 seconds after lock acquisition).

**Impact:** Voice switching is not instant. Rapid switching between voices is impractical.

**Mitigation:**
- Acceptable for a personal assistant: one voice per session
- Future enhancement: run multiple Piper instances as microservices for simultaneous multi-voice
- Voice switching is rare (user changes preference, not per-utterance)

### 8.8 WAV Format Lock-in

**Risk:** The plan specifies WAV audio. Some older browsers may have limited WAV decoding support in `AudioContext.decodeAudioData()`.

**Impact:** Niche — all modern browsers (Chrome, Firefox, Safari, Edge) support WAV decoding via Web Audio API.

**Mitigation:** Firefox, Chrome, Edge, and Safari all support WAV in `decodeAudioData()`. No action needed. If a browser doesn't support WAV, the fallback to `SpeechSynthesis` covers it.

### 8.9 Audio Interruption Behavior

**Decision:** Cancel-on-new. When a new utterance arrives while audio is playing, the current audio is stopped immediately and the new audio begins.

**Rationale:** For a personal assistant, the most recent response is the most relevant. Queuing utterances would cause a backlog after rapid exchanges; overlapping would be incoherent. Cancel-on-new matches the behavior of most voice assistants (Siri, Google Assistant).

**Implementation:** `currentSource.stop()` before starting the new `AudioBufferSourceNode`. Clear `onended` callback before stopping to prevent the animation from stopping prematurely.

**Tradeoff:** If a short utterance arrives immediately after a long one, the long one is cut off. This is acceptable — the user triggered the new response by sending a new message.

---

## 9. Alternatives Considered

### 9.1 Piper as Standalone HTTP Microservice

Piper ships a built-in HTTP server (`python3 -m piper.http_server -m <voice>`) on port 5000.

| Aspect | In-Process (chosen) | Standalone Microservice |
|--------|-------------------|----------------------|
| **Deployment** | Single service, one systemd unit | Two services, two systemd units |
| **Performance** | Zero IPC overhead, direct function call | HTTP overhead per request |
| **Resilience** | Piper crash takes down voice box | Independent restart, survives Piper crash |
| **Multi-voice** | One voice at a time, reload to switch | Run multiple instances on different ports |
| **Complexity** | One codebase, one Python env | Two Python envs, inter-process communication |

**Decision:** In-process, for simplicity. Multi-voice can be added later if needed.

### 9.2 Coqui TTS (XTTS-v2)

| Aspect | Piper | Coqui XTTS-v2 |
|--------|-------|---------------|
| **Voice quality** | Good (VITS) | Excellent (GPT-style) |
| **Voice cloning** | Not supported | Yes, 3-second sample |
| **Model size** | 35MB (medium) | 1.2GB |
| **Speed** | ~1× real-time on CPU | ~5× slower on CPU, needs GPU |
| **Maintenance** | Active (OHF) | Unmaintained (company disbanded) |
| **License** | GPL-3.0 | CPML (restrictive) |

**Decision:** Rejected. Quality is higher but the downsides (unmaintained, GPU requirement, 1.2GB model, restrictive license) outweigh the benefit.

### 9.3 Mimic 3 (Mycroft)

Mimic 3 is another VITS-based TTS engine from the Mycroft project.

| Aspect | Piper | Mimic 3 |
|--------|-------|---------|
| **Voices** | 40+ languages, good coverage | Fewer voices, limited en_GB selection |
| **Maintenance** | Active (OHF) | Minimal (Mycroft defunct) |
| **Install** | `pip install piper-tts` | Manual binary download |
| **Community** | Large (Home Assistant ecosystem) | Small |

**Decision:** Rejected. Piper has better voice selection and a larger community.

### 9.4 Kokoro / Sherpa-ONNX

Kokoro (82M parameters) is a newer TTS model that also runs on ONNX Runtime. Quality is reportedly good.

| Aspect | Piper | Kokoro |
|--------|-------|--------|
| **Voice selection** | 40+ languages, multiple voices each | Limited voices, primarily US English |
| **en_GB female** | Excellent (southern_english_female) | Not available |
| **Maintenance** | Active (OHF) | Newer, smaller community |
| **Integration** | `pip install piper-tts` | Manual model download |

**Decision:** Not pursued. Piper's British English female voice is proven. Kokoro lacks en_GB support.

### 9.5 Web Speech API (Status Quo)

| Aspect | Piper | Web Speech API (do nothing) |
|--------|-------|---------------------------|
| **Voice quality** | Neural, consistent | espeak-ng on Linux, varies by OS |
| **Voice control** | Full (speed, pitch, variation, volume) | Minimal (rate, pitch — browser-dependent) |
| **Offline** | Yes (server-side) | Yes (browser-native) |
| **Multi-client** | Identical across all clients | Drifts per browser/OS |

**Decision:** Replaced. The status quo delivers poor quality on Linux and inconsistent quality everywhere.

---

## 10. Edge Cases & Failure Modes

| Scenario | Expected Behavior | Implementation Detail |
|----------|------------------|----------------------|
| **Piper model fails to load** | Fall back to `SpeechSynthesis` for all requests | `PiperManager.load_voice()` returns False → `/speak` omits `audio` field |
| **ONNX Runtime crashes** | Catch exception, return 500, fallback on next request | Try/except around `run_in_executor`, log error, reset PiperManager state |
| **AudioContext blocked by browser** | Visual-only until user clicks, then resume | `AudioContext.resume()` on user interaction, "Click to enable audio" indicator |
| **New utterance interrupts playing audio** | Current audio stops, new audio begins | `currentSource.stop()` + clear `onended` before starting new source |
| **`playAudioFromBase64()` throws** | `stopSpeakingAnimation()` called, fallback to browser TTS | `try/catch` in SSE handler; `stopSpeakingAnimation()` in catch block |
| **Very long text (>200 chars)** | Synthesize as-is; Piper handles arbitrary length | Piper has no input length limit, but very long texts take proportionally longer |
| **Empty text** | Return 400 immediately | Already handled by existing validation in POST /speak |
| **Single character / punctuation** | Synthesize normally (Piper handles all valid input) | Test with ".", "!", "—" |
| **Voice model file missing at startup** | Clear error with setup instructions | `PiperManager.__init__()` raises `FileNotFoundError` with `"Run: bash setup.sh"` |
| **Voice model missing at `/vox/voice`** | Return 404 with download command | `POST /vox/voice` returns 404 with message including `python3 -m piper.download_voices <name>` |
| **Multiple rapid POST /speak** | Sequential synthesis via ThreadPoolExecutor + lock | `max_workers=1` + `_model_lock` provides double queuing |
| **`POST /vox/voice` during active synthesis** | Voice switch waits for synthesis to complete | `_model_lock` held by `synthesize_wav()` blocks `load_voice()` until synthesis finishes |
| **SSE client disconnect** | No error — client stops receiving events | SSE is fire-and-forget; disconnected clients simply miss subsequent events |
| **Non-UTF-8 text / emoji** | Piper may ignore or skip unsupported characters | Test with emoji, math symbols, mixed scripts |
| **Piper process OOM** | OS kills server.py → systemd restarts it | Standard systemd restart policy applies |
| **Browser doesn't support AudioContext** | Fall back to `speakText()` via SpeechSynthesis | `if (window.AudioContext || window.webkitAudioContext) { ... } else { speakFallback(text); }` |
| **Network partition (frontend can't reach server)** | SSE reconnects automatically | EventSource has built-in reconnection; no audio during reconnection period |
| **Server startup before Piper finishes loading** | Health endpoint returns `"piper": "loading"` | `is_loaded` property drives health response; startup takes ~2-4s extra |

---

## 11. Rollout Strategy

### Phase 1 — Validation
```bash
# Run setup script to install and verify Piper
bash setup.sh
# Listen to test audio output
aplay /tmp/piper-test.wav
```

### Phase 2 — Backend Integration
1. Add `PiperManager` class
2. Wire into server.py lifespan
3. Verify `/services/health` returns `"piper": "ready"` after startup
4. Verify `GET /vox/status` returns voice info
5. Verify `POST /speak` returns `audio` field

### Phase 3 — Frontend Integration
1. Add `audio-player.js`
2. Modify SSE handler
3. Verify audio plays in browser
4. Verify cancel-on-new behavior with two rapid requests
5. Verify voice selection dropdown

### Phase 4 — Graceful Degradation Testing
1. Rename model file → verify browser TTS fallback activates
2. Remove Piper package → verify fallback
3. Force `playAudioFromBase64()` to throw → verify `stopSpeakingAnimation()` called
4. Test with network-disconnected browser → confirm SSE reconnection

### Phase 5 — Full Cycle Test
1. Send command via terminal
2. Lucent generates response
3. Response text arrives via POST /speak
4. Audio plays through browser
5. Avatar animation syncs with audio and stops at correct time
6. Send second command while first audio is playing — verify cancel-on-new
7. Verify with mute/unmute toggle

---

## 12. Security Considerations

### 12.1 Audio Data Exposure

Synthesized audio passes through the server process memory briefly (during synthesis + base64 encoding) and over the SSE connection to the browser. On localhost, the SSE connection is not encrypted.

**Mitigation:** Standard for local-only services. If exposed remotely, wrap behind TLS (reverse proxy with nginx/Caddy).

### 12.2 Voice Model Integrity

Voice model files (`.onnx`) are downloaded from HuggingFace. ONNX models define a computation graph, which is generally safe. However, ONNX models can include custom operators implemented as native shared libraries — these execute arbitrary code at runtime. Piper's official voice models do not use custom operators, but this is a property of the specific model files, not the format.

**Mitigation:** Download only from the official HuggingFace repository (`rhasspy/piper-voices`). Verify file hashes against the repository's checksums if running in a security-sensitive context. Do not load voice models from untrusted sources.

### 12.3 Text-to-Speech Input Sanitization

Text submitted to Piper is synthesized as-is. There is no SSML injection risk (Piper doesn't support SSML), but very long texts could cause excessive CPU/memory consumption.

**Mitigation:** The existing `/speak` endpoint validates non-empty text. Consider adding a maximum text length (e.g., 5000 characters) if needed.

### 12.4 Audio Cache Side-Channel

The (currently not implemented) audio cache could leak information about what text has been synthesized if queryable from outside.

**Mitigation:** Not applicable — caching is not implemented in this plan. If added later, ensure cache is process-local only.

---

## 13. Glossary

| Term | Definition |
|------|------------|
| **base64** | Binary-to-text encoding scheme that represents binary data in ASCII string format (~33% size overhead) |
| **CUDA** | NVIDIA's parallel computing platform for GPU acceleration |
| **espeak-ng** | Open-source speech synthesizer (formant-based, sounds robotic) — the current Linux TTS backend |
| **EventSource** | Browser API for receiving Server-Sent Events over HTTP |
| **FastAPI** | Python web framework used by the voice box server |
| **GPL-3.0** | GNU General Public License v3 — open-source license |
| **lifespan** | FastAPI startup/shutdown context manager (replaces deprecated `@app.on_event`) |
| **ONNX** | Open Neural Network Exchange — a portable model format for ML inference |
| **ONNX Runtime** | Cross-platform inference engine for ONNX models |
| **PCM** | Pulse-Code Modulation — raw digital audio representation |
| **Piper** | Neural text-to-speech engine using VITS + ONNX Runtime |
| **RSS** | Resident Set Size — the portion of memory occupied by a process in RAM |
| **SAPI** | Microsoft Speech API — the Windows TTS backend |
| **SSE** | Server-Sent Events — HTTP-based streaming protocol (one-direction, server → client) |
| **SSML** | Speech Synthesis Markup Language — XML markup for controlling TTS |
| **VoiceInfo** | Dataclass: `name: str, language: str, quality: str, gender: str, sample_rate: int` |
| **VITS** | Conditional Variational Autoencoder with Adversarial Learning — a neural TTS architecture |
| **WAV** | Waveform Audio File Format — standard audio container for PCM data |
| **Web Speech API** | Browser API for speech synthesis (`window.speechSynthesis`) |
| **× real-time** | Speed ratio relative to audio duration. 1× real-time = 1 second of audio takes 1 second to synthesize |

---

## 14. How to Provide Feedback

This plan is distributed for review. Feedback is welcome on any aspect.

**Please consider:**

1. **Architecture decisions** — Is in-process Piper the right choice? Would a microservice be better?
2. **Voice selection** — Is `en_GB-southern_english_female-medium` the right voice? Are there better options?
3. **Audio delivery** — Base64 WAV over SSE is the simplest approach. Should we use WebSocket streaming instead?
4. **Interruption policy** — Is cancel-on-new the right behavior, or should utterances queue?
5. **Missing edge cases** — Are there failure modes not covered in §10?
6. **Implementation order** — Should any phase be reordered?
7. **Performance concerns** — Any scenarios where ~1× real-time CPU would be problematic?
8. **Alternative engines** — Is there a TTS engine that should be considered over Piper?

**Send feedback via:**
- [Repository issues](#)
- Direct message to author

---

## 15. Appendix A: Reference Implementations

### 15.1 Home Assistant Piper Integration

Home Assistant includes Piper as an officially supported Add-on and integration. Their implementation:
- Runs Piper as a standalone Docker container
- Exposes an HTTP API for synthesis
- Integrated into the Assist pipeline (wake word → STT → LLM → TTS)

Reference: [Home Assistant Piper Add-on](https://github.com/home-assistant/addons/blob/master/piper/README.md)

### 15.2 Piper Python API (Official Examples)

The `piper-tts` package includes a complete Python API reference:
- [Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
- [HTTP API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_HTTP.md)
- [CLI reference](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md)

### 15.3 Voice Samples

Listen to all available voices: [rhasspy.github.io/piper-samples](https://rhasspy.github.io/piper-samples/)

---

*End of plan. Version 1.1 — revised 2026-05-14.*
