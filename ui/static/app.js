// DOM elements
const currentText = document.getElementById('currentText');
const voiceSelect = document.getElementById('voiceSelect');
const themeToggle = document.getElementById('themeToggle');
const status = document.getElementById('status');
const waveform = document.getElementById('waveform');
const enableVoiceBtn = document.getElementById('enableVoice');
const voicePanelLabel = document.getElementById('voicePanelLabel');
const logContent = document.getElementById('logContent');

// State
let currentVoice = null;
let isSpeaking = false;
let voiceEnabled = false;
let lastLogContent = '';

// Load and populate available voices
function loadVoices() {
    const voices = window.speechSynthesis.getVoices();
    voiceSelect.innerHTML = '';

    voices.forEach((voice, index) => {
        const option = document.createElement('option');
        option.value = index;
        option.textContent = `${voice.name} (${voice.lang})`;
        voiceSelect.appendChild(option);
    });

    // Try to auto-select British English voice
    const britishVoices = voices.filter(v =>
        v.name.includes('Zira') ||
        (v.lang.includes('en-GB') && v.name.includes('Female'))
    );

    if (britishVoices.length > 0) {
        const selectedIndex = voices.indexOf(britishVoices[0]);
        voiceSelect.value = selectedIndex;
        currentVoice = britishVoices[0];
        status.textContent = `Voice: ${britishVoices[0].name}`;
    } else if (voices.length > 0) {
        voiceSelect.value = 0;
        currentVoice = voices[0];
    }
}

// Initialize voices when they load
window.speechSynthesis.onvoiceschanged = loadVoices;
loadVoices();

// Voice selection change
voiceSelect.addEventListener('change', (e) => {
    const voices = window.speechSynthesis.getVoices();
    currentVoice = voices[e.target.value];
    localStorage.setItem('selectedVoice', e.target.value);
    status.textContent = `Voice: ${currentVoice.name}`;
});

// Restore selected voice from localStorage
const savedVoice = localStorage.getItem('selectedVoice');
if (savedVoice && voiceSelect.options[savedVoice]) {
    voiceSelect.value = savedVoice;
    const voices = window.speechSynthesis.getVoices();
    currentVoice = voices[savedVoice];
}

// Enable voice output (requires user interaction)
function enableVoiceOutput() {
    voiceEnabled = true;
    enableVoiceBtn.classList.add('hidden');
    status.textContent = 'Voice enabled. Ready to speak.';

    // Test TTS with a small utterance to ensure it works
    const testUtterance = new SpeechSynthesisUtterance('');
    testUtterance.voice = currentVoice;
    window.speechSynthesis.speak(testUtterance);
}

// Text-to-speech
function speakText(text) {
    if (!voiceEnabled) {
        status.textContent = 'Voice not enabled. Click "Enable Voice" button.';
        currentText.textContent = text;
        return;
    }

    if (!currentVoice || !window.speechSynthesis) {
        console.error('Speech synthesis not available');
        status.textContent = 'Error: TTS not available';
        return;
    }

    // Cancel any ongoing speech
    window.speechSynthesis.cancel();

    // Display the text
    currentText.textContent = text;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = currentVoice;
    utterance.rate = 1.3;  // Slightly faster than normal
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    utterance.onstart = () => {
        isSpeaking = true;
        const scanner = document.getElementById('scanner');
        const speakingAnimation = document.getElementById('speakingAnimation');
        scanner.style.display = 'none';
        speakingAnimation.classList.remove('hidden');
        speakingAnimation.style.display = 'flex';
        waveform.classList.add('hidden');
        voicePanelLabel.textContent = 'AI VOICE BOX — SPEAKING';
        voicePanelLabel.classList.add('speaking');
        status.textContent = 'Speaking...';
    };

    utterance.onend = () => {
        isSpeaking = false;
        const scanner = document.getElementById('scanner');
        const speakingAnimation = document.getElementById('speakingAnimation');
        scanner.style.display = 'flex';
        speakingAnimation.classList.add('hidden');
        speakingAnimation.style.display = 'none';
        waveform.classList.add('hidden');
        voicePanelLabel.textContent = 'AI VOICE BOX — IDLE';
        voicePanelLabel.classList.remove('speaking');
        status.textContent = 'Ready';
    };

    utterance.onerror = (event) => {
        console.error('Speech error:', event);
        status.textContent = `Speech error: ${event.error}`;
        isSpeaking = false;
        const scanner = document.getElementById('scanner');
        const speakingAnimation = document.getElementById('speakingAnimation');
        scanner.style.display = 'flex';
        speakingAnimation.classList.add('hidden');
        speakingAnimation.style.display = 'none';
        waveform.classList.add('hidden');
        voicePanelLabel.textContent = 'AI VOICE BOX — IDLE';
        voicePanelLabel.classList.remove('speaking');
    };

    window.speechSynthesis.speak(utterance);
}

// Poll for speak requests from terminal
async function pollForSpeech() {
    // This endpoint will be called by terminal via curl
    // But the frontend needs a way to receive the text
    // We'll use Server-Sent Events or WebSocket for real-time updates
    // For now, this is handled via the /speak endpoint being called directly
}

// Poll for pending speech from terminal
async function pollForPendingSpeech() {
    try {
        const response = await fetch('/speak/pending');
        const data = await response.json();

        if (data.speech && data.speech.text) {
            speakText(data.speech.text);
        }
    } catch (error) {
        console.error('Error polling for speech:', error);
    }
}

// Set up polling for speech requests from terminal
function setupSpeechListener() {
    // Poll every 500ms for pending speech requests
    setInterval(pollForPendingSpeech, 500);

    status.textContent = 'Listening for speech requests...';
}

// Poll for log updates
async function pollForLog() {
    try {
        const response = await fetch('/log');
        const data = await response.json();
        if (data.content && data.content !== lastLogContent) {
            logContent.textContent = data.content;
            lastLogContent = data.content;
            logContent.scrollTop = logContent.scrollHeight;
        }
    } catch (error) {
        console.error('Error polling for log:', error);
    }
}

// Set up polling for log updates
function setupLogListener() {
    pollForLog();
    setInterval(pollForLog, 3000);
}

// Theme toggle
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    if (savedTheme === 'light') {
        document.body.classList.add('light-mode');
        themeToggle.textContent = '☀️';
    } else {
        themeToggle.textContent = '🌙';
    }
}

themeToggle.addEventListener('click', () => {
    const isLight = document.body.classList.toggle('light-mode');
    const theme = isLight ? 'light' : 'dark';
    localStorage.setItem('theme', theme);
    themeToggle.textContent = isLight ? '☀️' : '🌙';
});

// Enable voice button click handler
enableVoiceBtn.addEventListener('click', enableVoiceOutput);

initTheme();
setupSpeechListener();
setupLogListener();

status.textContent = 'Click "Enable Voice" to start';
