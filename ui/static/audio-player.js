// audio-player.js — Server-side Piper TTS audio playback (global scope)

(function () {
    let audioContext = null;
    let currentSource = null;

    function ensureAudioContext() {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        return audioContext;
    }

    async function playAudioFromBase64(base64Audio) {
        const ctx = ensureAudioContext();

        if (ctx.state === 'suspended') {
            await ctx.resume();
        }

        // Cancel-on-new: stop any currently playing audio
        if (currentSource) {
            currentSource.onended = null;
            try { currentSource.stop(); } catch (_) {}
            currentSource = null;
        }

        // Decode base64 → binary
        const binaryStr = atob(base64Audio);
        const bytes = new Uint8Array(binaryStr.length);
        for (let i = 0; i < binaryStr.length; i++) {
            bytes[i] = binaryStr.charCodeAt(i);
        }

        const audioBuffer = await ctx.decodeAudioData(bytes.buffer);

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);
        source.start(0);
        currentSource = source;

        source.onended = () => {
            if (currentSource === source) currentSource = null;
        };

        return source;
    }

    function stopAudio() {
        if (currentSource) {
            currentSource.onended = null;
            try { currentSource.stop(); } catch (_) {}
            currentSource = null;
        }
    }

    function isAudioContextAvailable() {
        return !!(window.AudioContext || window.webkitAudioContext);
    }

    // Expose on window
    window.AudioPlayer = { playAudioFromBase64, stopAudio, isAudioContextAvailable };
})();
