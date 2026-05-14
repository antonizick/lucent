# NX Vox — Voice Management Guide

**Last updated:** 2026-05-14  
**System:** Lucent Voice Box (port 8001)  
**Engine:** [Piper TTS](https://github.com/OHF-Voice/piper1-gpl) — local, neural, no cloud, no API key

---

## Table of Contents

1. [Overview](#1-overview)
2. [Browsing Available Voices](#2-browsing-available-voices)
3. [Downloading a Voice](#3-downloading-a-voice)
4. [Testing a Voice Before Installing](#4-testing-a-voice-before-installing)
5. [Making a Voice Available in the UI](#5-making-a-voice-available-in-the-ui)
6. [Assigning a Voice to an Avatar](#6-assigning-a-voice-to-an-avatar)
7. [Switching Voices at Runtime](#7-switching-voices-at-runtime)
8. [Adjusting Speech Speed](#8-adjusting-speech-speed)
9. [Currently Installed Voices](#9-currently-installed-voices)
10. [Removing a Voice](#10-removing-a-voice)
11. [Troubleshooting](#11-troubleshooting)
12. [Reference: URL Pattern for Downloads](#12-reference-url-pattern-for-downloads)

---

## 1. Overview

The Lucent Voice Box uses **Piper TTS** to generate natural-sounding speech server-side. Voice models are `.onnx` files stored locally in `ui/voices/`. They are never sent to the internet — all synthesis happens on your machine.

**Key facts:**
- Voices are discovered automatically by scanning `ui/voices/` — no code changes needed to add one
- Switching voices is instant via the dropdown or API
- Each avatar can have its own default voice (`ui/voice_config.json`)
- Model files are git-ignored (too large) — they must be downloaded manually on each machine

---

## 2. Browsing Available Voices

### Step 1 — Listen to voice samples online

Go to:

> **https://rhasspy.github.io/piper-samples/**

This page lets you listen to every available Piper voice in your browser. No login required. Voices are grouped by language. Click the play button next to any voice to hear a sample sentence.

- Focus on the **English (en_GB)** section for British English voices
- Focus on the **English (en_US)** section for American English voices
- The quality tier (`low`, `medium`, `high`) affects naturalness and model file size

### Step 2 — Note the voice name

When you find a voice you like, note its full name. The name format is always:

```
{language_code}-{voice_name}-{quality}
```

Examples:
- `en_GB-cori-high` — British English, "Cori", high quality
- `en_GB-alan-medium` — British English, "Alan", medium quality
- `en_US-lessac-medium` — American English, "Lessac", medium quality

### Step 3 — Find the download path on HuggingFace (optional verification)

All voice models live at:

> **https://huggingface.co/rhasspy/piper-voices/tree/main**

Navigate: `en/` → `en_GB/` → `{voice_name}/` → `{quality}/`

You will find two files you need:
- `{full-voice-name}.onnx` — the model weights (~10-200MB depending on quality)
- `{full-voice-name}.onnx.json` — the config (small, a few KB)

---

## 3. Downloading a Voice

All voice files go in `ui/voices/` relative to the Lucent project root (`/home/nick/dev/lucent/`).

### Template command

Run from the Lucent project root (`/home/nick/dev/lucent/`):

```bash
VOICES_DIR="ui/voices"
LANG="en_GB"           # Change to en_US or another code for other languages
VOICE_NAME="cori"      # The voice name part only (e.g. "cori", "alan", "jenny_dioco")
QUALITY="high"         # low | medium | high
FULL_NAME="${LANG}-${VOICE_NAME}-${QUALITY}"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/${LANG}/${VOICE_NAME}/${QUALITY}"

curl -L --progress-bar \
  -o "${VOICES_DIR}/${FULL_NAME}.onnx" \
  "${BASE}/${FULL_NAME}.onnx?download=true"

curl -L --progress-bar \
  -o "${VOICES_DIR}/${FULL_NAME}.onnx.json" \
  "${BASE}/${FULL_NAME}.onnx.json?download=true"

echo "Done. Files in ${VOICES_DIR}/:"
ls -lh "${VOICES_DIR}/${FULL_NAME}"*
```

### Real examples

**Download "Cori" British English, high quality:**
```bash
curl -L --progress-bar \
  -o ui/voices/en_GB-cori-high.onnx \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx?download=true"

curl -L --progress-bar \
  -o ui/voices/en_GB-cori-high.onnx.json \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx.json?download=true"
```

**Download "Lessac" American English, medium quality:**
```bash
curl -L --progress-bar \
  -o ui/voices/en_US-lessac-medium.onnx \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true"

curl -L --progress-bar \
  -o ui/voices/en_US-lessac-medium.onnx.json \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true"
```

### File size guide

| Quality tier | Typical model size | Memory usage (approx) |
|---|---|---|
| `low` | ~10 MB | ~50 MB RAM |
| `medium` | ~35-65 MB | ~150 MB RAM |
| `high` | ~100-200 MB | ~300-500 MB RAM |

> **Note:** If a downloaded file is only a few bytes (< 1000 bytes), the download URL was wrong — the file contains an error message, not a real model. Verify the voice name and path carefully.

---

## 4. Testing a Voice Before Installing

You can synthesize a test audio file from the command line before loading the voice into the server. Run from the `ui/` directory:

```bash
cd /home/nick/dev/lucent/ui

python3 -c "
from piper import PiperVoice
import wave, io

voice = PiperVoice.load('voices/en_GB-cori-high.onnx')
out = io.BytesIO()
with wave.open(out, 'wb') as f:
    voice.synthesize_wav('Hello, this is a test of the Cori voice.', f)

with open('/tmp/piper-test.wav', 'wb') as f:
    f.write(out.getvalue())

print(f'Synthesized {len(out.getvalue()):,} bytes — saved to /tmp/piper-test.wav')
"
```

Then play the file:
```bash
aplay /tmp/piper-test.wav      # Linux (ALSA)
# or open in your audio player of choice
```

Replace the `.onnx` filename with whichever voice you want to test.

---

## 5. Making a Voice Available in the UI

**No server restart is needed.** The voice list endpoint (`GET /vox/voices`) scans `ui/voices/` at call-time. Simply:

1. Drop the `.onnx` and `.onnx.json` files into `ui/voices/`
2. Reload the Voice Box page in your browser

The new voice will appear in the voice dropdown automatically. Both files must be present — the server ignores `.onnx` files that have no matching `.onnx.json` companion.

---

## 6. Assigning a Voice to an Avatar

Avatar-to-voice assignments are stored in `ui/voice_config.json`. Editing this file takes effect immediately — no restart needed.

### Method A — API call (recommended)

```bash
curl -X POST http://localhost:8001/vox/config \
  -H "Content-Type: application/json" \
  -d '{"avatar": "AvatarName", "voice": "en_GB-cori-high"}'
```

Replace `AvatarName` with the avatar folder name from `ui/static/avatars/` (e.g. `Lucent`, `Emma`, `Alex`, `Karen`). Replace the voice name with the full voice name (without `.onnx`).

**Example — assign "Jenny" voice to the Emma avatar:**
```bash
curl -X POST http://localhost:8001/vox/config \
  -H "Content-Type: application/json" \
  -d '{"avatar": "Emma", "voice": "en_GB-jenny_dioco-medium"}'
```

### Method B — Edit the JSON file directly

Open `ui/voice_config.json` in any text editor:

```json
{
  "avatar_voices": {
    "Lucent": "en_GB-cori-high",
    "Emma": "en_GB-jenny_dioco-medium",
    "Alex": "en_GB-alan-medium",
    "Karen": "en_GB-cori-high"
  },
  "default_voice": "en_GB-cori-high"
}
```

Add a new entry under `avatar_voices`:
```json
"MyNewAvatar": "en_GB-cori-medium"
```

The `default_voice` is used for any avatar that has no specific mapping.

### Verifying the current config

```bash
curl -s http://localhost:8001/vox/config | python3 -m json.tool
```

---

## 7. Switching Voices at Runtime

### Via the browser UI

Use the **voice dropdown** in the Voice Box web UI (`http://localhost:8001`). Selecting a voice switches the server to that model immediately — the next `POST /speak` call will use the new voice.

### Via API

**Switch the active voice:**
```bash
curl -X POST http://localhost:8001/vox/voice \
  -H "Content-Type: application/json" \
  -d '{"voice": "en_GB-alan-medium"}'
```

Response:
```json
{
  "status": "switched",
  "voice": "en_GB-alan-medium",
  "previous": "en_GB-cori-high",
  "duration_ms": 480
}
```

**Check the currently active voice and stats:**
```bash
curl -s http://localhost:8001/vox/status | python3 -m json.tool
```

```json
{
  "voice": "en_GB-alan-medium",
  "sample_rate": 22050,
  "loaded": true,
  "synthesis_count": 42,
  "total_audio_seconds": 84.5,
  "mean_synthesis_ms": 870.0,
  "uptime_seconds": 3600.0
}
```

**List all installed voices:**
```bash
curl -s http://localhost:8001/vox/voices | python3 -m json.tool
```

---

## 8. Adjusting Speech Speed

Speech speed is controlled by Piper's `length_scale` parameter. Lower values produce faster speech; higher values produce slower speech.

### Via the browser UI

Use the **SPD slider** in the Voice Box header (between the voice dropdown and the theme toggle). Drag left for faster, right for slower.

- **Range:** 0.50 (roughly 2× faster) to 1.50 (noticeably slower)
- **Default:** 1.00 (model's natural speed)
- **Step:** 0.05

When you move the mouse off the slider after adjusting, the setting is saved immediately and the avatar speaks a confirmation. The speed persists across page reloads and server restarts — it is written to `ui/voice_config.json`.

### Via API

**Set the speed:**
```bash
curl -X POST http://localhost:8001/vox/speed \
  -H "Content-Type: application/json" \
  -d '{"speed": 0.85}'
```

Response:
```json
{ "status": "ok", "speed": 0.85 }
```

**Check current speed:**
```bash
curl -s http://localhost:8001/vox/status | python3 -m json.tool
```

The `speed` field in the response shows the active `length_scale`.

### Speed reference

| `length_scale` | Effective speed | Character |
|---|---|---|
| `0.50` | ~2× faster | Very fast — may reduce clarity |
| `0.75` | ~1.3× faster | Noticeably quick |
| `0.85` | ~1.2× faster | Slightly brisk (good default for dense text) |
| `1.00` | Normal | Model's natural pace |
| `1.25` | ~0.8× | Slightly measured |
| `1.50` | ~0.67× | Clearly slower — useful for complex content |

Speed is global — it applies to all voices and avatars. Switching avatar or voice does not reset the speed.

---

## 9. Currently Installed Voices

As of 2026-05-14, the following voices are installed in `ui/voices/`:

| Voice name | Gender | Quality | Size | Notes |
|---|---|---|---|---|
| `en_GB-cori-high` | Female | High | ~109 MB | **Default voice for Lucent and Karen** |
| `en_GB-jenny_dioco-medium` | Female | Medium | ~61 MB | Default voice for Emma |
| `en_GB-alan-medium` | Male | Medium | ~61 MB | Default voice for Alex |
| `en_GB-northern_english_male-medium` | Male | Medium | ~61 MB | Available in dropdown |

All are British English (`en_GB`).

---

## 10. Removing a Voice

1. Delete the two files from `ui/voices/`:
   ```bash
   rm ui/voices/en_GB-alan-medium.onnx ui/voices/en_GB-alan-medium.onnx.json
   ```

2. If that voice is mapped to an avatar in `voice_config.json`, update the mapping:
   ```bash
   curl -X POST http://localhost:8001/vox/config \
     -H "Content-Type: application/json" \
     -d '{"avatar": "Alex", "voice": "en_GB-northern_english_male-medium"}'
   ```

3. Reload the browser page — the voice will no longer appear in the dropdown.

> **Warning:** Do not delete the voice that is currently active. Switch to another voice first via `POST /vox/voice`, then delete.

---

## 11. Troubleshooting

### Voice appears in the dropdown but produces no sound

The ONNX model may be corrupted or incomplete. Check the file size:
```bash
ls -lh ui/voices/
```
If the `.onnx` file is less than 1 MB, it downloaded incorrectly. Delete it and re-download.

### "Voice not found" error when switching

The voice name in the API call must exactly match the filename in `ui/voices/` without the `.onnx` extension. Check available names:
```bash
ls ui/voices/*.onnx | sed 's|ui/voices/||; s|\.onnx||'
```

### Server startup takes longer than usual

Each Piper model loads in 2-4 seconds at startup. High-quality models (`-high`) take longer than medium. This is normal — the `/services/health` endpoint will show `"piper": "loading"` until the model is ready, then `"piper": "ready"`.

### Voice is working via curl but browser plays no audio

The browser requires a user gesture (a click) before it can play audio. Click anywhere on the Voice Box page first. A status indicator at the bottom reads `"Click anywhere to enable speech"` until the first click.

### Downloaded file is only ~15 bytes

The HuggingFace URL path was wrong. The file contains `Entry not found`. Double-check:
- The language code matches (`en_GB` vs `en_US`)
- The voice name spelling (e.g. `jenny_dioco` not `jenny-dioco`)
- The quality tier exists for that voice (some voices only have `low`, not `medium` or `high`)

To verify what's available for a voice:
```bash
curl -s "https://huggingface.co/api/models/rhasspy/piper-voices?full=false" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
siblings = data.get('siblings', [])
# Change 'cori' to the voice name you want to check
matches = [s['rfilename'] for s in siblings if 'cori' in s['rfilename'] and '.onnx' in s['rfilename']]
print('\n'.join(matches))
"
```

---

## 12. Reference: URL Pattern for Downloads

The HuggingFace download URL follows this pattern:

```
https://huggingface.co/rhasspy/piper-voices/resolve/main/
  {lang_family}/
    {lang_code}/
      {voice_name}/
        {quality}/
          {lang_code}-{voice_name}-{quality}.onnx?download=true
```

Where:
- `{lang_family}` — always `en` for English voices
- `{lang_code}` — e.g. `en_GB`, `en_US`, `en_AU`
- `{voice_name}` — the voice identifier, e.g. `cori`, `alan`, `jenny_dioco`
- `{quality}` — `low`, `medium`, or `high`

**Example — `en_GB-cori-high`:**
```
https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx?download=true
```

**Example — `en_US-lessac-medium`:**
```
https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true
```

Append `?download=true` to force the file download rather than a HuggingFace preview page.
