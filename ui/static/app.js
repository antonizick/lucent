// DOM elements
const currentText = document.getElementById('currentText');
const currentTextContent = document.getElementById('currentTextContent');
const currentTextTimestamp = document.getElementById('currentTextTimestamp');
const voiceSelect = document.getElementById('voiceSelect');
const themeToggle = document.getElementById('themeToggle');
const activityLogBtn = document.getElementById('activityLogBtn');
const status = document.getElementById('status');
const voicePanelLabel = document.getElementById('voicePanelLabel');
const logContent = document.getElementById('logContent');
const servicesList = document.getElementById('servicesList');

// State
let currentVoice = null;
let isSpeaking = false;
let lastLogContent = '';
let fadeTimeout = null;
let speechEnabled = false;

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

// Update timestamp display
function updateTimestamp() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    currentTextTimestamp.textContent = `${hours}:${minutes}:${seconds}`;
}

// Enable speech on first user interaction
function enableSpeech() {
    if (!speechEnabled) {
        speechEnabled = true;
        status.textContent = 'Speech enabled. Ready.';
        status.classList.remove('not-ready');
        // Remove the click listener after first interaction
        document.removeEventListener('click', enableSpeech);
    }
}

// Text-to-speech
function speakText(text) {
    if (!speechEnabled) {
        status.textContent = 'Click anywhere to enable speech.';
        currentTextContent.textContent = text;
        updateTimestamp();
        return;
    }

    if (!currentVoice || !window.speechSynthesis) {
        console.error('Speech synthesis not available');
        status.textContent = 'Error: TTS not available';
        return;
    }

    // Cancel any ongoing speech
    window.speechSynthesis.cancel();

    // Clear any pending fade timeout
    if (fadeTimeout) {
        clearTimeout(fadeTimeout);
        fadeTimeout = null;
    }

    // Reset opacity to full
    currentText.style.opacity = '1';

    // Display the text with timestamp
    currentTextContent.textContent = text;
    updateTimestamp();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = currentVoice;
    utterance.rate = 1.3;  // Slightly faster than normal
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    utterance.onstart = () => {
        isSpeaking = true;
        const scanner = document.getElementById('scanner');
        const speakingAnimation = document.getElementById('speakingAnimation');

        // Clear any pending fade timeout when speech starts
        if (fadeTimeout) {
            clearTimeout(fadeTimeout);
            fadeTimeout = null;
        }

        // Ensure text is full opacity while speaking
        currentText.style.opacity = '1';

        scanner.style.display = 'none';
        speakingAnimation.classList.remove('hidden');
        speakingAnimation.style.display = 'flex';
        voicePanelLabel.textContent = 'AI VOICE BOX — SPEAKING';
        voicePanelLabel.classList.add('speaking');
        status.textContent = 'Speaking...';
    };

    utterance.onend = () => {
        // Set timeout to fade text after 2 minutes
        fadeTimeout = setTimeout(() => {
            currentText.style.opacity = '0.2';
            fadeTimeout = null;
        }, 120000);

        isSpeaking = false;
        const scanner = document.getElementById('scanner');
        const speakingAnimation = document.getElementById('speakingAnimation');
        scanner.style.display = 'flex';
        speakingAnimation.classList.add('hidden');
        speakingAnimation.style.display = 'none';
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

        // Clear any pending fade timeout on error
        if (fadeTimeout) {
            console.log('[utterance.onerror] Clearing pending fade timeout');
            clearTimeout(fadeTimeout);
            fadeTimeout = null;
        }

        // Reset opacity on error
        currentText.style.opacity = '1';

        scanner.style.display = 'flex';
        speakingAnimation.classList.add('hidden');
        speakingAnimation.style.display = 'none';
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

// Poll for service health
async function pollServiceHealth() {
    try {
        const response = await fetch('/services/health');
        const data = await response.json();
        renderServices(data.services);
    } catch (error) {
        console.error('Error polling service health:', error);
    }
}

// Service descriptions
const serviceDescriptions = {
    'Ollama Local inference engine': 'Local AI model processing - handles conversational requests and generates responses',
    'Voice box': 'Web-based voice output interface - speaks responses and displays status',
    'Discord bot': 'Discord bot service - listens for messages and routes them to processing',
    'Discord poller': 'Message queue consumer - fetches pending Discord messages for processing',
    'Discord monitor': 'Response handler - processes instructions and sends replies back to Discord',
    'Lucent server': 'Central backend API - manages queues, memory, and coordinates all services'
};

// Render services list
function renderServices(services) {
    servicesList.innerHTML = '';
    services.forEach(service => {
        const item = document.createElement('div');
        item.className = `service-item ${service.status}`;
        item.setAttribute('data-description', serviceDescriptions[service.name] || 'Service status unknown');

        const dot = document.createElement('span');
        dot.className = `service-dot ${service.status}`;

        const name = document.createElement('span');
        name.className = 'service-name';
        name.textContent = service.name;

        item.appendChild(dot);
        item.appendChild(name);
        servicesList.appendChild(item);

        // Set tooltip position based on available space
        item.addEventListener('mouseenter', () => {
            setTimeout(() => {
                const rect = item.getBoundingClientRect();
                const tooltipWidth = 500; // approximate tooltip width
                const padding = 10;

                // Check if tooltip would overflow left
                if (rect.left < tooltipWidth + padding) {
                    item.classList.add('tooltip-right');
                    item.classList.remove('tooltip-left');
                } else {
                    item.classList.add('tooltip-left');
                    item.classList.remove('tooltip-right');
                }
            }, 0);
        });
    });
}

// Set up polling for service health
function setupServiceListener() {
    pollServiceHealth();
    setInterval(pollServiceHealth, 10000);
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

// Activity log button
activityLogBtn.addEventListener('click', () => {
    // Open activity log in a new tab
    window.open('/activity-log-viewer', '_blank');
});

// Constrain animation to viewport top
function constrainAnimationHeight() {
    const speakingAnimation = document.getElementById('speakingAnimation');
    if (speakingAnimation) {
        const rect = speakingAnimation.getBoundingClientRect();
        const spaceAbove = rect.top; // Distance from top of viewport to animation
        const containerHeight = 120; // Container height in pixels

        // Calculate how much height we can use (in percentage of container)
        // If space above is 200px and container is 120px, we can go to 200/120 = 166%
        const maxHeightPercent = Math.max(100, (spaceAbove / containerHeight) * 100);

        // Set CSS variable for max animation height
        document.documentElement.style.setProperty('--max-animation-height', maxHeightPercent + '%');
    }
}

// Recalculate on resize
window.addEventListener('resize', constrainAnimationHeight);

// Initial calculation after page loads
window.addEventListener('load', constrainAnimationHeight);

initTheme();
setupSpeechListener();
setupLogListener();
setupServiceListener();

// Listen for first click to enable speech (browser autoplay policy)
document.addEventListener('click', enableSpeech);

status.textContent = 'Click anywhere to enable speech';
status.classList.add('not-ready');
