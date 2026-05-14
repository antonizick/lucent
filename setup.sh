#!/usr/bin/env bash
# setup.sh — NX Vox environment setup
set -e

VOICES_DIR="ui/voices"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB"

download_voice() {
    local name="$1"
    local hf_path="$2"
    local label="$3"
    echo "=== ${label} (${name}) ==="
    if [ -f "$VOICES_DIR/${name}.onnx" ] && [ "$(stat -c%s "$VOICES_DIR/${name}.onnx")" -gt 1000 ]; then
        echo "Already present — skipping"
    else
        curl -L --progress-bar -o "$VOICES_DIR/${name}.onnx" "${BASE_URL}/${hf_path}/${name}.onnx?download=true"
        curl -L --progress-bar -o "$VOICES_DIR/${name}.onnx.json" "${BASE_URL}/${hf_path}/${name}.onnx.json?download=true"
        echo "Downloaded"
    fi
}

echo "=== Installing Piper TTS ==="
if python3 -c "import piper" 2>/dev/null; then
    echo "piper-tts already installed"
elif [ -f "piper_tts-"*".whl" ]; then
    pip install piper_tts-*.whl
else
    pip install piper-tts
fi

echo ""
echo "=== Voice directory ==="
mkdir -p "$VOICES_DIR"

# Female voices
download_voice "en_GB-cori-high"          "cori/high"                   "Cori (female, high quality)"
download_voice "en_GB-jenny_dioco-medium" "jenny_dioco/medium"          "Jenny Dioco (female, medium)"

# Male voices
download_voice "en_GB-alan-medium"               "alan/medium"                "Alan (male, medium)"
download_voice "en_GB-northern_english_male-medium" "northern_english_male/medium" "Northern English Male (medium)"

echo ""
echo "=== Verifying synthesis ==="
python3 -c "
from piper import PiperVoice
import wave, io
voice = PiperVoice.load('$VOICES_DIR/en_GB-cori-high.onnx')
out = io.BytesIO()
with wave.open(out, 'wb') as f:
    voice.synthesize_wav('Setup complete.', f)
print(f'Synthesis OK: {len(out.getvalue()):,} bytes')
"

echo ""
echo "=== Setup complete ==="
echo "Run the voice box with: cd ui && bash start.sh"
