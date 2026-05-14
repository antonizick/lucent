// DOM elements
const currentText = document.getElementById('currentText');
const currentTextContent = document.getElementById('currentTextContent');
const currentTextTimestamp = document.getElementById('currentTextTimestamp');
const avatarSelect = document.getElementById('avatarSelect');
const voiceSelect = document.getElementById('voiceSelect');
const themeToggle = document.getElementById('themeToggle');
const activityLogBtn = document.getElementById('activityLogBtn');
const status = document.getElementById('status');
const voicePanelLabel = document.getElementById('voicePanelLabel');
const logContent = document.getElementById('logContent');
const servicesList = document.getElementById('servicesList');
const refreshTimer = document.getElementById('refreshTimer');
const speedSlider = document.getElementById('speedSlider');
const speedValue = document.getElementById('speedValue');

// State
let currentVoice = null;
let isSpeaking = false;
let lastLogContent = '';
let fadeTimeout = null;
let speechEnabled = false;
let currentAgent = null;  // null = Lucent mode, string = named agent
let currentLogTab = 'daily';  // 'daily', 'weekly', 'memory', or 'security'
let lastWeeklyContent = '';
let lastMemoryContent = '';
let lastSecurityContent = '';
let refreshCountdown = 30;
let refreshTimerInterval = null;

// Load and populate available voices from server Piper API
async function loadVoices() {
    voiceSelect.innerHTML = '';

    // Add "None" option for muting
    const noneOption = document.createElement('option');
    noneOption.value = 'none';
    noneOption.textContent = 'None (muted)';
    voiceSelect.appendChild(noneOption);

    try {
        const resp = await fetch('/vox/voices');
        if (resp.ok) {
            const data = await resp.json();
            const savedVoice = localStorage.getItem('selectedVoice');

            data.voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.name;
                const genderTag = voice.gender !== 'unknown' ? ` (${voice.gender})` : '';
                option.textContent = `${voice.name}${genderTag}`;
                voiceSelect.appendChild(option);
            });

            // Select current server voice or saved preference
            const target = savedVoice && savedVoice !== 'none' ? savedVoice : data.current;
            if (target && voiceSelect.querySelector(`option[value="${target}"]`)) {
                voiceSelect.value = target;
                currentVoice = target;
            } else if (data.current) {
                voiceSelect.value = data.current;
                currentVoice = data.current;
            }

            if (currentVoice && currentVoice !== 'none') {
                status.textContent = `Voice: ${currentVoice}`;
            }
        }
    } catch (err) {
        // Fall back to browser TTS if server voices unavailable
        console.warn('Server voices unavailable, using browser TTS:', err);
        const voices = window.speechSynthesis.getVoices();
        voices.forEach((voice, index) => {
            const option = document.createElement('option');
            option.value = `browser:${index}`;
            option.textContent = `${voice.name} (${voice.lang})`;
            voiceSelect.appendChild(option);
        });
        if (voices.length > 0) {
            voiceSelect.value = `browser:0`;
            currentVoice = `browser:0`;
        }
    }
}

loadVoices();

// Speed control — init from server, persist on change
async function initSpeed() {
    try {
        const resp = await fetch('/vox/status');
        if (!resp.ok) return;
        const data = await resp.json();
        if (typeof data.speed === 'number') {
            speedSlider.value = data.speed;
            speedValue.textContent = data.speed.toFixed(2) + '×';
        }
    } catch (e) { /* server not ready yet */ }
}

let speedDebounce = null;
speedSlider.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    speedValue.textContent = val.toFixed(2) + '×';
    clearTimeout(speedDebounce);
    speedDebounce = setTimeout(async () => {
        try {
            await fetch('/vox/speed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speed: val }),
            });
        } catch (err) {
            console.warn('Speed update failed:', err);
        }
    }, 300);
});

initSpeed();

// Voice selection change — switch server voice if it's a Piper voice
voiceSelect.addEventListener('change', async (e) => {
    const val = e.target.value;
    localStorage.setItem('selectedVoice', val);

    if (val === 'none') {
        currentVoice = null;
        status.textContent = 'Voice: Muted (visualizations only)';
        return;
    }

    currentVoice = val;

    if (!val.startsWith('browser:')) {
        // Switch server voice
        try {
            await fetch('/vox/voice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: val }),
            });
            status.textContent = `Voice: ${val}`;
        } catch (err) {
            console.error('Voice switch failed:', err);
        }
    } else {
        const idx = parseInt(val.replace('browser:', ''));
        const voices = window.speechSynthesis.getVoices();
        status.textContent = `Voice: ${voices[idx]?.name || val}`;
    }
});

// Update avatar→voice mapping when user manually changes voice
// (persists the new preference for the current avatar to the server config)
async function saveAvatarVoicePreference(avatarName, voiceName) {
    if (!avatarName || !voiceName || voiceName === 'none' || voiceName.startsWith('browser:')) return;
    try {
        voiceConfigCache = null; // invalidate cache
        await fetch('/vox/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ avatar: avatarName, voice: voiceName }),
        });
    } catch (_) {}
}

// Voice config cache
let voiceConfigCache = null;

async function getVoiceConfig() {
    if (!voiceConfigCache) {
        try {
            const resp = await fetch('/vox/config');
            if (resp.ok) voiceConfigCache = await resp.json();
        } catch (_) {}
    }
    return voiceConfigCache || { avatar_voices: {}, default_voice: null };
}

async function applyAvatarVoice(avatarName) {
    try {
        const config = await getVoiceConfig();
        const mapped = config.avatar_voices[avatarName] || config.default_voice;
        if (!mapped) return;

        // Only switch if different from current
        if (mapped === currentVoice) return;

        await fetch('/vox/voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ voice: mapped }),
        });
        currentVoice = mapped;

        // Update dropdown to reflect new voice
        if (voiceSelect.querySelector(`option[value="${mapped}"]`)) {
            voiceSelect.value = mapped;
        }
    } catch (err) {
        console.warn('Avatar voice switch failed:', err);
    }
}

// Avatar auto-switching helpers
function findAvatarByName(name) {
    if (!name) return null;
    const lower = name.toLowerCase();
    return avatarManager.avatars.find(a => a.toLowerCase() === lower) || null;
}

async function selectAvatarProfile(name) {
    avatarSelect.value = name || '';
    await window.character.setAvatar(name || null);
    localStorage.setItem('selectedAvatar', name || '');
    // Switch voice to match this avatar
    if (name) await applyAvatarVoice(name);
}

async function applyAgentAvatar(agentName) {
    const isLucent = !agentName || agentName === 'Lucent';
    const wasLucent = !currentAgent;

    if (isLucent) {
        currentAgent = null;
        // Restore Lucent's avatar via fallback chain
        const last = localStorage.getItem('lucentAvatar');
        const target = findAvatarByName(last) ||
                       findAvatarByName('Lucent') ||
                       findAvatarByName('Emma') ||
                       avatarManager.avatars[0] ||
                       null;
        await selectAvatarProfile(target || 'Lucent');
    } else {
        // Save Lucent's current avatar before switching away
        if (wasLucent) {
            localStorage.setItem('lucentAvatar', avatarSelect.value || '');
        }
        currentAgent = agentName;
        const match = findAvatarByName(agentName);
        if (match) {
            await selectAvatarProfile(match);
        } else {
            // No matching avatar image, but still switch voice
            await applyAvatarVoice(agentName);
        }
    }
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

    // If muted (currentVoice is null), just display text and animations without speaking
    if (!currentVoice) {
        isSpeaking = true;
        const scanner = document.getElementById('scanner');
        const speakingAnimation = document.getElementById('speakingAnimation');
        scanner.style.display = 'none';
        speakingAnimation.classList.remove('hidden');
        speakingAnimation.style.display = 'flex';
        voicePanelLabel.textContent = 'AI VOICE BOX — VISUALIZING';
        voicePanelLabel.classList.add('speaking');
        status.textContent = 'Visualizing (muted)...';

        if (window.character) {
            window.character.startSpeaking();
        }

        // Auto-stop after 3 seconds in muted mode
        setTimeout(async () => {
            isSpeaking = false;
            scanner.style.display = 'flex';
            speakingAnimation.classList.add('hidden');
            speakingAnimation.style.display = 'none';
            voicePanelLabel.textContent = 'AI VOICE BOX — IDLE';
            voicePanelLabel.classList.remove('speaking');
            status.textContent = 'Ready';

            if (window.character) {
                await window.character.stopSpeaking();
            }

            fadeTimeout = setTimeout(() => {
                currentText.style.opacity = '0.2';
                fadeTimeout = null;
            }, 120000);
        }, 3000);
        return;
    }

    if (!window.speechSynthesis) {
        console.error('Speech synthesis not available');
        status.textContent = 'Error: TTS not available';
        return;
    }

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

        // Start character animation
        if (window.character) {
            window.character.startSpeaking();
        }
    };

    utterance.onend = async () => {
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

        // Stop character animation and wait for transition
        if (window.character) {
            await window.character.stopSpeaking();
        }
    };

    utterance.onerror = async (event) => {
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

        // Stop character animation on error and wait for transition
        if (window.character) {
            await window.character.stopSpeaking();
        }
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

// Set up SSE streaming for speech requests (multi-client broadcast)
function setupSpeechListener() {
    const eventSource = new EventSource('/speak/stream');

    eventSource.onopen = () => {
        status.textContent = 'Listening for speech requests...';
    };

    eventSource.onmessage = async (event) => {
        try {
            const data = JSON.parse(event.data);
            if (!data || !data.text) return;

            // Always update text display
            currentTextContent.textContent = data.text;
            updateTimestamp();
            if (fadeTimeout) {
                clearTimeout(fadeTimeout);
                fadeTimeout = null;
            }
            currentText.style.opacity = '1';

            if (currentVoice === 'none' || currentVoice === null) {
                // Muted — visualize only
                speakText(data.text);
                return;
            }

            if (data.audio && speechEnabled && window.AudioPlayer && window.AudioPlayer.isAudioContextAvailable()) {
                // Server-side Piper audio
                startSpeakingAnimation();
                try {
                    const source = await window.AudioPlayer.playAudioFromBase64(data.audio);
                    source.onended = () => {
                        stopSpeakingAnimation();
                        fadeTimeout = setTimeout(() => {
                            currentText.style.opacity = '0.2';
                            fadeTimeout = null;
                        }, 120000);
                    };
                } catch (err) {
                    console.error('Audio playback failed:', err);
                    stopSpeakingAnimation();
                    if (window.speechSynthesis && currentVoice && !currentVoice.startsWith('browser:')) {
                        speakFallback(data.text);
                    } else {
                        speakText(data.text);
                    }
                }
            } else {
                // Browser TTS fallback
                speakText(data.text);
            }
        } catch (error) {
            console.error('Error parsing speech event:', error);
        }
    };

    eventSource.onerror = () => {
        status.textContent = 'Reconnecting to speech stream...';
        eventSource.close();
        setTimeout(setupSpeechListener, 3000);
    };
}

function startSpeakingAnimation() {
    isSpeaking = true;
    const scanner = document.getElementById('scanner');
    const speakingAnimation = document.getElementById('speakingAnimation');
    scanner.style.display = 'none';
    speakingAnimation.classList.remove('hidden');
    speakingAnimation.style.display = 'flex';
    voicePanelLabel.textContent = 'AI VOICE BOX — SPEAKING';
    voicePanelLabel.classList.add('speaking');
    status.textContent = 'Speaking...';
    if (window.character) window.character.startSpeaking();
}

async function stopSpeakingAnimation() {
    isSpeaking = false;
    const scanner = document.getElementById('scanner');
    const speakingAnimation = document.getElementById('speakingAnimation');
    scanner.style.display = 'flex';
    speakingAnimation.classList.add('hidden');
    speakingAnimation.style.display = 'none';
    voicePanelLabel.textContent = 'AI VOICE BOX — IDLE';
    voicePanelLabel.classList.remove('speaking');
    status.textContent = 'Ready';
    if (window.character) await window.character.stopSpeaking();
}

function speakFallback(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterance);
}

// Poll for log updates
async function pollForLog() {
    try {
        if (currentLogTab === 'daily') {
            const response = await fetch('/log');
            const data = await response.json();
            if (data.content && data.content !== lastLogContent) {
                logContent.textContent = data.content;
                lastLogContent = data.content;
                logContent.scrollTop = logContent.scrollHeight;
            }
        } else if (currentLogTab === 'weekly') {
            const response = await fetch('/log/weekly');
            const data = await response.json();
            if (data.content && data.content !== lastWeeklyContent) {
                logContent.textContent = data.content;
                lastWeeklyContent = data.content;
                logContent.scrollTop = logContent.scrollHeight;
            }
        } else if (currentLogTab === 'memory') {
            const response = await fetch('/log/memory');
            const data = await response.json();
            if (data.content && data.content !== lastMemoryContent) {
                logContent.textContent = data.content;
                lastMemoryContent = data.content;
                logContent.scrollTop = logContent.scrollHeight;
            }
        } else if (currentLogTab === 'security') {
            const response = await fetch('/security/report');
            const data = await response.json();
            if (data.content && data.content !== lastSecurityContent) {
                logContent.textContent = data.content;
                lastSecurityContent = data.content;
                logContent.scrollTop = logContent.scrollHeight;
            }
        }
    } catch (error) {
        console.error('Error polling for log:', error);
    }
}

// Switch log tab
function switchLogTab(tab) {
    currentLogTab = tab;

    // Clear cache for this tab to force a fresh fetch
    if (tab === 'daily') {
        lastLogContent = '';
    } else if (tab === 'weekly') {
        lastWeeklyContent = '';
    } else if (tab === 'memory') {
        lastMemoryContent = '';
    } else if (tab === 'security') {
        lastSecurityContent = '';
    }

    // Update button states
    document.querySelectorAll('.log-tab').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');

    // Update labels
    document.getElementById('logLabelDaily').classList.toggle('hidden', tab !== 'daily');
    document.getElementById('logLabelWeekly').classList.toggle('hidden', tab !== 'weekly');
    document.getElementById('logLabelMemory').classList.toggle('hidden', tab !== 'memory');
    document.getElementById('logLabelSecurity').classList.toggle('hidden', tab !== 'security');

    // Clear content and poll immediately
    logContent.textContent = 'Loading...';
    pollForLog();
}

// Update refresh timer countdown
function startRefreshTimer() {
    refreshCountdown = 30;
    refreshTimer.textContent = '30s';

    // Clear any existing interval
    if (refreshTimerInterval) {
        clearInterval(refreshTimerInterval);
    }

    // Count down every second
    refreshTimerInterval = setInterval(() => {
        refreshCountdown--;
        if (refreshCountdown >= 0) {
            refreshTimer.textContent = refreshCountdown + 's';
        }
        if (refreshCountdown < 0) {
            clearInterval(refreshTimerInterval);
        }
    }, 1000);
}

// Set up polling for log updates
function setupLogListener() {
    // Load immediately on page load
    pollForLog();
    startRefreshTimer();

    // Poll every 30 seconds
    setInterval(() => {
        pollForLog();
        startRefreshTimer();
    }, 30000);

    // Set up tab switching with immediate fetch
    document.querySelectorAll('.log-tab').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchLogTab(e.target.dataset.tab);
        });
    });
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

    // Add service items
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

// Backup status polling
async function pollBackupStatus() {
    try {
        const response = await fetch('/backup/status');
        const data = await response.json();
        updateBackupStatus(data);
    } catch (error) {
        console.error('Error fetching backup status:', error);
    }
}

function updateBackupStatus(data) {
    const lucentTime = document.getElementById('lucentBackupTime');
    const memoryTime = document.getElementById('memoryBackupTime');
    const lucentDot = document.getElementById('lucentBackupDot');
    const memoryDot = document.getElementById('memoryBackupDot');

    if (!lucentTime || !memoryTime || !lucentDot || !memoryDot) {
        return;
    }

    function formatTime(backup) {
        if (!backup) return { time: 'Unknown', dotClass: 'backup-red', textClass: 'offline' };
        const timeStr = `${backup.time} ${backup.date_display} (${backup.hours_ago}h ago)`;
        // Determine dot color based on status
        let dotClass = 'backup-green';
        if (backup.status === 'yellow') {
            dotClass = 'backup-yellow';
        } else if (backup.status === 'red') {
            dotClass = 'backup-red';
        }
        // Text color: cyan for green/yellow (warning acceptable), grey for red (critical)
        const textClass = (backup.status === 'red') ? 'offline' : 'online';
        return { time: timeStr, dotClass, textClass };
    }

    const lucent = formatTime(data.lucent);
    const memory = formatTime(data.memory);

    lucentTime.textContent = lucent.time;
    memoryTime.textContent = memory.time;

    // Set dot color classes
    lucentDot.className = `service-dot ${lucent.dotClass}`;
    memoryDot.className = `service-dot ${memory.dotClass}`;

    // Set text color based on status
    const lucentItem = lucentDot.closest('.service-item');
    const memoryItem = memoryDot.closest('.service-item');

    if (lucentItem) {
        lucentItem.classList.toggle('online', lucent.textClass === 'online');
        lucentItem.classList.toggle('offline', lucent.textClass === 'offline');
    }

    if (memoryItem) {
        memoryItem.classList.toggle('online', memory.textClass === 'online');
        memoryItem.classList.toggle('offline', memory.textClass === 'offline');
    }
}

function setupBackupListener() {
    pollBackupStatus();
    setInterval(pollBackupStatus, 30000);
}

// Poll for agent state changes
async function pollForAgentState() {
    try {
        const res = await fetch('/agent/current');
        const data = await res.json();
        const agentName = data.agent === 'Lucent' ? null : data.agent;
        if (agentName !== currentAgent) {
            await applyAgentAvatar(agentName);
        }
    } catch (e) {
        // Silent failure - agent polling is optional
    }
}

// Poll for available agents
async function pollForAgents() {
    try {
        const response = await fetch('/agents');
        const data = await response.json();
        renderAgentsDirectory(data.agents);
    } catch (error) {
        console.error('Error polling for agents:', error);
    }
}

// Render agents directory table
function renderAgentsDirectory(agents) {
    const container = document.getElementById('agentsContainer');

    // Preserve the font size before clearing
    const savedFontSize = container.style.fontSize;

    container.innerHTML = '';

    if (!agents || agents.length === 0) {
        container.innerHTML = '<p class="no-agents">No agents available</p>';
        // Restore font size
        if (savedFontSize) {
            container.style.fontSize = savedFontSize;
        }
        return;
    }

    const table = document.createElement('table');
    table.className = 'agents-table';

    agents.forEach(agent => {
        const row = document.createElement('tr');
        row.className = 'agent-row';

        const nameCell = document.createElement('td');
        nameCell.className = 'agent-name';
        nameCell.textContent = agent.name;

        const descCell = document.createElement('td');
        descCell.className = 'agent-description';
        descCell.textContent = agent.description;

        row.appendChild(nameCell);
        row.appendChild(descCell);
        table.appendChild(row);
    });

    container.appendChild(table);

    // Restore font size after rendering
    if (savedFontSize) {
        container.style.fontSize = savedFontSize;
    }
}

// Track agents panel state and polling interval
let agentsPollInterval = null;
let agentsPanelCollapsed = true; // Default to collapsed

// Font size management
const MIN_FONT_SIZE = 9;
const MAX_FONT_SIZE = 18;
const FONT_SIZE_STEP = 1;

let logFontSize = parseInt(localStorage.getItem('logFontSize')) || 11;
let agentsFontSize = parseInt(localStorage.getItem('agentsFontSize')) || 11;

// Font size adjustment functions
function adjustFontSize(panel, increase) {
    let fontSize;
    let storageKey;
    let element;

    if (panel === 'log') {
        fontSize = logFontSize;
        storageKey = 'logFontSize';
        element = document.getElementById('logContent');
    } else if (panel === 'agents') {
        fontSize = agentsFontSize;
        storageKey = 'agentsFontSize';
        element = document.querySelector('.agents-table');
        if (!element) element = document.getElementById('agentsContainer');
    }

    if (!element) return;

    const newSize = increase ?
        Math.min(fontSize + FONT_SIZE_STEP, MAX_FONT_SIZE) :
        Math.max(fontSize - FONT_SIZE_STEP, MIN_FONT_SIZE);

    element.style.fontSize = newSize + 'px';
    localStorage.setItem(storageKey, newSize);

    if (panel === 'log') {
        logFontSize = newSize;
    } else if (panel === 'agents') {
        agentsFontSize = newSize;
    }
}

// Apply saved font sizes on load
function applySavedFontSizes() {
    const logContent = document.getElementById('logContent');
    const agentsContainer = document.getElementById('agentsContainer');

    if (logContent) {
        logContent.style.fontSize = logFontSize + 'px';
    }

    if (agentsContainer) {
        agentsContainer.style.fontSize = agentsFontSize + 'px';
    }
}

// Toggle agents panel collapse state
function toggleAgentsPanel() {
    const panel = document.querySelector('.agents-panel');
    const container = document.getElementById('agentsContainer');
    const toggle = document.getElementById('agentsToggle');

    agentsPanelCollapsed = !agentsPanelCollapsed;

    if (agentsPanelCollapsed) {
        panel.classList.add('collapsed');
        container.classList.add('hidden');
        // Stop polling when collapsed
        if (agentsPollInterval) {
            clearInterval(agentsPollInterval);
            agentsPollInterval = null;
        }
    } else {
        panel.classList.remove('collapsed');
        container.classList.remove('hidden');
        // Resume polling when expanded
        pollForAgents();
        agentsPollInterval = setInterval(pollForAgents, 300000);
    }

    // Save state to localStorage
    localStorage.setItem('agentsPanelCollapsed', agentsPanelCollapsed);
}

// Set up polling for agents directory
function setupAgentsListener() {
    // Start with collapsed state (default true)
    const panel = document.querySelector('.agents-panel');
    const container = document.getElementById('agentsContainer');

    if (agentsPanelCollapsed) {
        panel.classList.add('collapsed');
        container.classList.add('hidden');
    } else {
        // Only poll if not collapsed
        pollForAgents();
        agentsPollInterval = setInterval(pollForAgents, 300000);
    }

    // Add event listeners
    const toggleBtn = document.getElementById('agentsToggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleAgentsPanel);
    }

    const agentsFontUp = document.getElementById('agentsFontUp');
    const agentsFontDown = document.getElementById('agentsFontDown');
    if (agentsFontUp) agentsFontUp.addEventListener('click', () => adjustFontSize('agents', true));
    if (agentsFontDown) agentsFontDown.addEventListener('click', () => adjustFontSize('agents', false));
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
applySavedFontSizes();

// Set up font size controls for log panel
const logFontUp = document.getElementById('logFontUp');
const logFontDown = document.getElementById('logFontDown');
if (logFontUp) logFontUp.addEventListener('click', () => adjustFontSize('log', true));
if (logFontDown) logFontDown.addEventListener('click', () => adjustFontSize('log', false));

setupSpeechListener();
setupLogListener();
setupServiceListener();
setupBackupListener();
setupAgentsListener();

// Poll for agent state changes every 2 seconds
setInterval(pollForAgentState, 2000);

// Initialize avatar manager and character animator
const characterImg = document.getElementById('characterFrame');
const characterPanel = document.getElementById('characterPanel');
const avatarManager = new AvatarManager();
window.character = new CharacterAnimator(characterImg, characterPanel, avatarManager);

// Load and populate avatar dropdown
async function loadAvatars() {
    try {
        const avatars = await avatarManager.discoverAvatars();
        avatarSelect.innerHTML = '';

        // Always add "No Avatar" option for explicit deselection
        const noAvatarOption = document.createElement('option');
        noAvatarOption.value = '';
        noAvatarOption.textContent = 'No Avatar';
        avatarSelect.appendChild(noAvatarOption);

        avatars.forEach(avatar => {
            const option = document.createElement('option');
            option.value = avatar;
            option.textContent = avatar;
            avatarSelect.appendChild(option);
        });

        // Initialize with Lucent avatar using fallback chain
        await applyAgentAvatar(null);
    } catch (error) {
        console.error('Error loading avatars:', error);
        avatarSelect.innerHTML = '<option value="">No Avatar</option>';
    }
}

// Handle avatar selection change
avatarSelect.addEventListener('change', async (e) => {
    const avatar = e.target.value || null;
    localStorage.setItem('selectedAvatar', avatar || '');
    if (!currentAgent) {
        localStorage.setItem('lucentAvatar', avatar || '');
    }
    await window.character.setAvatar(avatar);
    // Switch to this avatar's configured voice
    if (avatar) await applyAvatarVoice(avatar);
});

loadAvatars();

// Listen for first click to enable speech (browser autoplay policy)
document.addEventListener('click', enableSpeech);

status.textContent = 'Click anywhere to enable speech';
status.classList.add('not-ready');

// Portal: Services panel mouseover/mouseout handlers with dynamic positioning
const voicePanel = document.getElementById('voicePanel');
const servicesPanel = document.getElementById('servicesPanel');

if (voicePanel && servicesPanel) {
    let pendingPositionUpdate = null;
    let isServicesPanelVisible = false;

    // Throttled positioning using requestAnimationFrame
    function updateServicesPanelPosition(mouseX, mouseY) {
        if (pendingPositionUpdate) {
            cancelAnimationFrame(pendingPositionUpdate);
        }
        pendingPositionUpdate = requestAnimationFrame(() => {
            if (isServicesPanelVisible) {
                // Get panel dimensions to position based on right/bottom edges
                const panelWidth = servicesPanel.offsetWidth;
                const panelHeight = servicesPanel.offsetHeight;

                // Minimum 100px separation from cursor on right and bottom edges
                const minGap = 100;

                // Position: right edge 100px left of cursor, bottom edge 100px above cursor
                const offsetX = -(panelWidth + minGap);
                const offsetY = -(panelHeight + minGap);

                servicesPanel.style.position = 'fixed';
                servicesPanel.style.left = (mouseX + offsetX) + 'px';
                servicesPanel.style.top = (mouseY + offsetY) + 'px';
            }
        });
    }

    // Show services on mouseover voice panel
    voicePanel.addEventListener('mouseenter', function(e) {
        isServicesPanelVisible = true;
        servicesPanel.classList.add('visible');
        updateServicesPanelPosition(e.clientX, e.clientY);
    });

    // Track mouse position and update services panel position
    voicePanel.addEventListener('mousemove', function(e) {
        if (isServicesPanelVisible) {
            updateServicesPanelPosition(e.clientX, e.clientY);
        }
    });

    // Hide services on mouseout voice panel
    voicePanel.addEventListener('mouseleave', function() {
        isServicesPanelVisible = false;
        servicesPanel.classList.remove('visible');
        servicesPanel.style.position = 'absolute';
        servicesPanel.style.left = '';
        servicesPanel.style.top = '';
        if (pendingPositionUpdate) {
            cancelAnimationFrame(pendingPositionUpdate);
        }
    });
}

// Portal: Log panel height calculation based on right column
function updateLogPanelHeight() {
    const characterPanel = document.querySelector('.character-panel');
    const voicePanel = document.querySelector('.voice-panel');
    const logPanel = document.querySelector('.log-panel');

    if (characterPanel && voicePanel && logPanel) {
        // Get combined height of right column elements
        const characterHeight = characterPanel.offsetHeight;
        const voiceHeight = voicePanel.offsetHeight;
        const combinedHeight = characterHeight + voiceHeight;

        // Only set if we have valid measurements (not 0)
        if (combinedHeight > 0) {
            // Calculate 85% of combined height
            const targetHeight = combinedHeight * 0.85;

            // Apply to log panel max-height
            logPanel.style.maxHeight = targetHeight + 'px';
        }
    }
}

// Call on initial load with longer delay to ensure DOM is ready
setTimeout(updateLogPanelHeight, 500);

// Update on window resize
window.addEventListener('resize', updateLogPanelHeight);

// Update when avatar changes (since avatar height might change)
if (avatarSelect) {
    avatarSelect.addEventListener('change', function() {
        setTimeout(updateLogPanelHeight, 300);
    });
}
