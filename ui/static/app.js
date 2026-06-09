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
let currentLogTab = 'daily';  // 'daily', 'weekly', 'memory', 'reminders', 'insights', or 'email'
let lastWeeklyContent = '';
let lastMemoryContent = '';
let lastRemindersContent = '';
let lastInsightsData = null;
let insightsInterval = null;
let lastProposalsData = null;
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
let speedDirty = false;

speedSlider.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    speedValue.textContent = val.toFixed(2) + '×';
    speedDirty = true;
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

speedSlider.addEventListener('mouseleave', async () => {
    if (!speedDirty) return;
    speedDirty = false;
    clearTimeout(speedDebounce);
    const val = parseFloat(speedSlider.value);
    try {
        await fetch('/vox/speed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ speed: val }),
        });
        await fetch('/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: 'The new speech speed default parameter specifications have been received.' }),
        });
    } catch (err) {
        console.warn('Speed confirmation failed:', err);
    }
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

            // Log Discord source responses
            if (data.source === 'discord') {
                console.log('[SPEECH] Discord response received and displayed:', data.text.substring(0, 80));
            }

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
        } else if (currentLogTab === 'reminders') {
            const response = await fetch('/log/reminders');
            const data = await response.json();
            if (data.content && data.content !== lastRemindersContent) {
                logContent.textContent = data.content;
                lastRemindersContent = data.content;
                logContent.scrollTop = 0;
            }
        } else if (currentLogTab === 'email-search') {
            loadEmailMonitor();
        }
    } catch (error) {
        console.error('Error polling for log:', error);
    }
}

// Convert ANSI color codes to HTML
function ansiToHtml(text) {
    const ansiRegex = /\033\[([\d;]+)m/g;
    const colorMap = {
        '31': 'color: #e74c3c;',      // Red
        '33': 'color: #f39c12;',      // Yellow
        '38;5;208': 'color: #ff8c00;' // Orange
    };

    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    // Replace ANSI codes with HTML spans
    html = html.replace(/\033\[([0-9;]+)m([^\033]*)/g, (match, code, content) => {
        const style = colorMap[code];
        if (style) {
            return `<span style="${style}">${content}</span>`;
        }
        return content;
    });

    return html;
}

// Insights polling — independent 5-minute interval
async function pollInsights() {
    try {
        const response = await fetch('/log/insights');
        const data = await response.json();
        const sig = JSON.stringify(data);
        if (sig !== JSON.stringify(lastInsightsData)) {
            lastInsightsData = data;
            logContent.innerHTML = renderInsights(data);
        }
        await loadProposals();
    } catch (error) {
        console.error('Error polling insights:', error);
    }
}

// ── NERO Insights rendering ──────────────────────────────────

function openFilePath(path) {
    try {
        console.log('Opening file:', path);
        // Use the view-file endpoint to display/download the file
        const viewUrl = `/view-file?path=${encodeURIComponent(path)}`;
        console.log('View URL:', viewUrl);
        window.open(viewUrl, '_blank');
    } catch (error) {
        console.error('Error opening file:', error);
    }
}

// Event delegation for clickable file links
if (logContent) {
    logContent.addEventListener('click', (e) => {
        const link = e.target.closest('.clickable-label');
        if (link && link.dataset.path) {
            e.preventDefault();
            openFilePath(link.dataset.path);
        }
    });
}

function insightsRow(label, value, filePath = null) {
    const labelHtml = filePath
        ? `<a href="#" class="insights-label clickable-label" data-path="${filePath}">${label}</a>`
        : `<span class="insights-label">${label}</span>`;
    return `<div class="insights-row">${labelHtml}<span class="insights-value">${value}</span></div>`;
}

function insightsRowWithLimit(label, value, limit, utilization, filePath = null) {
    const labelHtml = filePath
        ? `<a href="#" class="insights-label clickable-label" data-path="${filePath}">${label}</a>`
        : `<span class="insights-label">${label}</span>`;
    const utilizationBar = `<span class="insights-util" title="Utilization: ${utilization}%">[${utilization}%]</span>`;
    return `<div class="insights-row">${labelHtml}<span class="insights-value">${value} <span class="insights-limit">/ ${limit}</span> ${utilizationBar}</span></div>`;
}

function insightsSection(title, rows) {
    return `<div class="insights-section"><div class="insights-sechdr">${title}</div>${rows.join('')}</div>`;
}

function renderInsights(data) {
    if (data.error) {
        return `<div class="insights-panel"><div class="insights-err">Error: ${data.error}</div></div>`;
    }
    const { corpus, skills, reflection, curator } = data;
    const now = new Date().toLocaleTimeString();
    let h = `<div class="insights-panel">`;
    h += `<div class="insights-ts">NERO SELF-IMPROVEMENT INSIGHTS — ${now}</div>`;

    // Memory Corpus
    const ltmemValue = `${corpus.ltmemory.lines}/${corpus.ltmemory.line_limit} lines · ${corpus.ltmemory.size_kb}/${corpus.ltmemory.size_limit_kb} KB <span class="insights-util" title="Utilization: ${corpus.ltmemory.utilization_pct}%">[${corpus.ltmemory.utilization_pct}%]</span>`;
    const corpusRows = [
        `<div class="insights-row"><a href="#" class="insights-label clickable-label" data-path="${corpus.ltmemory.path}">LTMemory.md</a><span class="insights-value">${ltmemValue}</span></div>`,
        insightsRow('LTMemory.archive',  `${corpus.ltmemory_archive.lines} lines · ${corpus.ltmemory_archive.size_kb} KB`, corpus.ltmemory_archive.path),
        insightsRow('Auto-memory',       `${corpus.auto_memory_files} files · ${corpus.auto_memory_lines} lines`, corpus.auto_memory_path),
        insightsRowWithLimit('Daily notes', `${corpus.daily_notes_7d} files · ${corpus.daily_lines_7d} lines`, `${corpus.daily_notes_limit_days} days`, corpus.daily_notes_utilization_pct, corpus.daily_notes_path),
        insightsRow('Recall index',      `${corpus.recall_index_chunks} chunks`),
    ];
    h += insightsSection('MEMORY CORPUS', corpusRows);

    // Skill Library
    if (skills.error) {
        h += insightsSection('SKILL LIBRARY', [`<div class="insights-err">Error: ${skills.error}</div>`]);
    } else {
        const rows = [
            insightsRow('Live skills',  `<span class="insights-hi">${skills.total_live}</span>`, skills.skills_path),
            insightsRow('Protected',    skills.protected_count),
            insightsRow('Archived',     skills.archived),
        ];
        if (skills.by_state && Object.keys(skills.by_state).length) {
            const s = Object.entries(skills.by_state).map(([k,v]) => `${k}: ${v}`).join('  ');
            rows.push(insightsRow('By state', s));
        }
        if (skills.top_used && skills.top_used.length) {
            rows.push(`<div class="insights-subhdr">Top Used</div>`);
            skills.top_used.forEach(s => rows.push(insightsRow(`&nbsp;&nbsp;${s.slug}`, `${s.uses} uses · ${s.last || '—'}`)));
        }
        h += insightsSection('SKILL LIBRARY', rows);
    }

    // Reflection Loop
    if (reflection.error) {
        h += insightsSection('REFLECTION LOOP', [`<div class="insights-err">Error: ${reflection.error}</div>`]);
    } else {
        const pending = (reflection.by_status || {}).pending || 0;
        const rows = [
            insightsRow('Status',      `<span class="${reflection.enabled ? 'insights-ok' : 'insights-warn'}">${reflection.enabled ? '✓ enabled' : '✗ disabled'} &nbsp;(${reflection.mode} mode)</span>`),
            insightsRow('Last run',    reflection.last_run),
            insightsRow('Gate',        `${reflection.gate_hit_rate} &nbsp;(${reflection.gate_yes} yes / ${reflection.gate_no} no)`),
            insightsRow('Proposals',   reflection.proposals_total),
        ];
        if (pending > 0) {
            rows.push(insightsRow('Pending review', `<span class="insights-warn">⚡ ${pending} — reflect.py review</span>`));
        }
        if (reflection.by_status && Object.keys(reflection.by_status).length) {
            const s = Object.entries(reflection.by_status).map(([k,v]) => `${k}: ${v}`).join('  ');
            rows.push(insightsRow('By status', s));
        }
        if (reflection.by_type && Object.keys(reflection.by_type).length) {
            const s = Object.entries(reflection.by_type).map(([k,v]) => `${k}: ${v}`).join('  ');
            rows.push(insightsRow('By type', s));
        }
        h += insightsSection('REFLECTION LOOP', rows);
    }

    // Curator
    if (curator.error) {
        h += insightsSection('CURATOR', [`<div class="insights-err">Error: ${curator.error}</div>`]);
    } else {
        const rows = [
            insightsRow('Last run', curator.last_run),
            insightsRowWithLimit('Live sessions', curator.ltmemory_live_sessions, curator.ltmemory_live_sessions_limit, curator.ltmemory_utilization_pct, curator.ltmemory_path),
            insightsRow('Archived sessions', curator.ltmemory_archive_sessions, curator.ltmemory_archive_path),
        ];
        h += insightsSection('CURATOR', rows);
    }

    // Proposals panel (loaded separately via loadProposals())
    h += `<div id="proposalsPanel" class="proposals-panel-placeholder"></div>`;

    // Skills Listing
    if (skills.all_skills && skills.all_skills.length > 0) {
        const skillsRows = [];
        skillsRows.push(`<div class="skills-list">`);
        skills.all_skills.forEach(skill => {
            const protectedBadge = skill.protected ? ' 🔒' : '';
            const uses = skill.use_count > 0 ? ` · ${skill.use_count} uses` : '';
            const lastUsed = skill.last_used ? ` · last: ${skill.last_used.substring(0, 10)}` : '';
            const skillNameHtml = skill.path
                ? `<a href="#" class="skill-name clickable-label" data-path="${skill.path}">${skill.slug}</a>`
                : `<span class="skill-name">${skill.slug}</span>`;
            skillsRows.push(`<div class="skill-item">${skillNameHtml}<span class="skill-meta">${skill.state}${protectedBadge}${uses}${lastUsed}</span></div>`);
        });
        skillsRows.push(`</div>`);
        h += insightsSection('SKILLS LISTING', skillsRows);
    }

    h += `</div>`;
    return h;
}

// ── NERO Proposals panel ──────────────────────────────────────

async function loadProposals() {
    const panel = document.getElementById('proposalsPanel');
    if (!panel) return;
    try {
        const res = await fetch('/reflect/proposals');
        const data = await res.json();
        if (JSON.stringify(data) === JSON.stringify(lastProposalsData)) return;
        lastProposalsData = data;
        panel.outerHTML = renderProposals(data);
    } catch (e) {
        const p = document.getElementById('proposalsPanel');
        if (p) p.innerHTML = `<div class="insights-err">Failed to load proposals: ${e.message}</div>`;
    }
}

function renderProposals(data) {
    const { proposals, counts } = data;
    const pending = counts.pending || 0;
    const badge = pending > 0 ? `<span class="proposals-badge">${pending}</span>` : '';
    let h = `<div id="proposalsPanel" class="insights-section proposals-section">`;
    h += `<div class="insights-sechdr">PROPOSALS ${badge}</div>`;

    // Counts row
    const parts = [];
    if (counts.pending)  parts.push(`<span class="insights-warn">${counts.pending} pending</span>`);
    if (counts.applied)  parts.push(`<span class="insights-ok">${counts.applied} applied</span>`);
    if (counts.rejected) parts.push(`<span style="color:#888">${counts.rejected} rejected</span>`);
    if (parts.length) h += `<div class="proposals-counts">${parts.join(' &nbsp;·&nbsp; ')}</div>`;

    if (!proposals.length) {
        h += `<div class="proposals-empty">No pending proposals.</div>`;
    } else {
        proposals.forEach(p => {
            const typeClass = `ptype-${p.type.replace(/_/g, '-')}`;
            const preview = p.content.length > 300 ? p.content.substring(0, 300) + '…' : p.content;
            const escaped = preview.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            const contentEscaped = p.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            h += `<div class="proposal-card" data-id="${p.id}">`;
            h += `<div class="proposal-header">`;
            h += `  <span class="proposal-type ${typeClass}">${p.type}</span>`;
            h += `  <span class="proposal-target">${p.target}</span>`;
            h += `  <span class="proposal-id">#${p.id}</span>`;
            h += `</div>`;
            h += `<div class="proposal-reason">${p.reason.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>`;
            h += `<div id="pcontent-${p.id}" class="proposal-content-container">`;
            h += `  <pre class="proposal-content">${escaped}</pre>`;
            h += `</div>`;
            h += `<div class="proposal-actions">`;
            h += `  <button class="proposal-btn refine-btn" onclick="toggleRefineMode('${p.id}', ${JSON.stringify(contentEscaped)})">Refine</button>`;
            h += `  <button class="proposal-btn apply-btn" onclick="proposalAction('apply','${p.id}')">Apply</button>`;
            h += `  <button class="proposal-btn reject-btn" onclick="proposalAction('reject','${p.id}')">Reject</button>`;
            h += `</div>`;
            h += `<div id="refine-editor-${p.id}" class="refine-editor" style="display:none;">`;
            h += `  <textarea id="refine-textarea-${p.id}" class="refine-textarea">${contentEscaped}</textarea>`;
            h += `  <div class="refine-actions">`;
            h += `    <button class="proposal-btn save-btn" onclick="saveRefinement('${p.id}')">Save</button>`;
            h += `    <button class="proposal-btn cancel-btn" onclick="toggleRefineMode('${p.id}')">Cancel</button>`;
            h += `  </div>`;
            h += `</div>`;
            h += `<div class="proposal-msg" id="pmsg-${p.id}"></div>`;
            h += `</div>`;
        });
    }
    h += `</div>`;
    return h;
}

async function proposalAction(action, id) {
    const msgEl = document.getElementById(`pmsg-${id}`);
    const card = document.querySelector(`.proposal-card[data-id="${id}"]`);
    if (msgEl) { msgEl.textContent = action === 'apply' ? 'Applying…' : 'Rejecting…'; msgEl.className = 'proposal-msg'; }
    try {
        const res = await fetch(`/reflect/${action}/${id}`, { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
            if (card) {
                card.classList.add('proposal-done');
                card.querySelector('.proposal-actions').innerHTML =
                    `<span class="${action === 'apply' ? 'insights-ok' : ''}" style="color:${action==='apply'?'#4caf50':'#888'}">${action === 'apply' ? '✓ Applied' : '✗ Rejected'}</span>`;
            }
            if (msgEl) { msgEl.textContent = data.msg; msgEl.className = 'proposal-msg proposal-ok'; }
            // Refresh after short delay
            setTimeout(() => { lastProposalsData = null; loadProposals(); }, 800);
        } else {
            if (msgEl) { msgEl.textContent = data.msg || 'Failed'; msgEl.className = 'proposal-msg proposal-err'; }
        }
    } catch (e) {
        if (msgEl) { msgEl.textContent = e.message; msgEl.className = 'proposal-msg proposal-err'; }
    }
}

function toggleRefineMode(id, currentContent) {
    const contentDiv = document.getElementById(`pcontent-${id}`);
    const editorDiv = document.getElementById(`refine-editor-${id}`);
    const actionsDiv = document.querySelector(`.proposal-card[data-id="${id}"] .proposal-actions`);

    if (editorDiv.style.display === 'none') {
        contentDiv.style.display = 'none';
        editorDiv.style.display = 'block';
        actionsDiv.style.opacity = '0.5';
        actionsDiv.style.pointerEvents = 'none';
        const textarea = document.getElementById(`refine-textarea-${id}`);
        textarea.focus();
    } else {
        contentDiv.style.display = 'block';
        editorDiv.style.display = 'none';
        actionsDiv.style.opacity = '1';
        actionsDiv.style.pointerEvents = 'auto';
    }
}

async function saveRefinement(id) {
    const textarea = document.getElementById(`refine-textarea-${id}`);
    const newContent = textarea.value.trim();
    const msgEl = document.getElementById(`pmsg-${id}`);

    if (!newContent) {
        if (msgEl) { msgEl.textContent = 'Content cannot be empty'; msgEl.className = 'proposal-msg proposal-err'; }
        return;
    }

    if (msgEl) { msgEl.textContent = 'Saving refinement…'; msgEl.className = 'proposal-msg'; }

    try {
        const res = await fetch(`/reflect/refine/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: newContent })
        });
        const data = await res.json();
        if (data.ok) {
            toggleRefineMode(id);
            if (msgEl) { msgEl.textContent = 'Refinement saved'; msgEl.className = 'proposal-msg proposal-ok'; }
            // Update the preview
            const contentDiv = document.getElementById(`pcontent-${id}`);
            const preview = newContent.length > 300 ? newContent.substring(0, 300) + '…' : newContent;
            const escaped = preview.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            contentDiv.innerHTML = `<pre class="proposal-content">${escaped}</pre>`;
        } else {
            if (msgEl) { msgEl.textContent = data.msg || 'Failed to save'; msgEl.className = 'proposal-msg proposal-err'; }
        }
    } catch (e) {
        if (msgEl) { msgEl.textContent = 'Error: ' + e.message; msgEl.className = 'proposal-msg proposal-err'; }
    }
}

// Switch log tab
function switchLogTab(tab) {
    // Stop insights interval when leaving that tab
    if (currentLogTab === 'insights' && tab !== 'insights') {
        if (insightsInterval) {
            clearInterval(insightsInterval);
            insightsInterval = null;
        }
    }

    currentLogTab = tab;

    // Clear cache for this tab to force a fresh fetch
    if (tab === 'daily') {
        lastLogContent = '';
    } else if (tab === 'weekly') {
        lastWeeklyContent = '';
    } else if (tab === 'memory') {
        lastMemoryContent = '';
    } else if (tab === 'reminders') {
        lastRemindersContent = '';
    } else if (tab === 'insights') {
        lastInsightsData = null;
    } else if (tab === 'email-search') {
        loadEmailMonitor();
        loadEmailFeedback();
        pollPSTStatus();
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
    document.getElementById('logLabelReminders').classList.toggle('hidden', tab !== 'reminders');
    document.getElementById('logLabelInsights').classList.toggle('hidden', tab !== 'insights');
    document.getElementById('logLabelEmailSearch').classList.toggle('hidden', tab !== 'email-search');

    // Show/hide appropriate panels
    const logHeader = document.querySelector('.log-header');
    const logContentElement = document.getElementById('logContent');
    const emailSearchPanel = document.getElementById('emailSearchPanel');

    // Always show header (tabs are needed for navigation)
    if (logHeader) logHeader.classList.remove('hidden');

    // When email-search is active: hide main log content, show email panel
    if (tab === 'email-search') {
        if (logContentElement) logContentElement.classList.add('hidden');
        if (emailSearchPanel) emailSearchPanel.classList.remove('hidden');
    } else {
        // For other tabs: show main content, hide email panel
        if (logContentElement) logContentElement.classList.remove('hidden');
        if (emailSearchPanel) emailSearchPanel.classList.add('hidden');
    }

    // Clear content and poll immediately
    if (tab === 'email-search') {
        // email-search is manual — no auto-poll
    } else if (tab === 'insights') {
        logContent.innerHTML = '<div class="insights-panel"><div class="insights-ts">Loading...</div></div>';
        lastInsightsData = null;
        pollInsights();
        insightsInterval = setInterval(pollInsights, 300000); // 5 minutes
    } else {
        logContent.textContent = 'Loading...';
        pollForLog();
    }
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

    // Email search functionality
    const emailSearchInput = document.getElementById('emailSearchInput');
    const emailSearchBtn = document.getElementById('emailSearchBtn');
    const emailSearchContent = document.getElementById('emailSearchContent');

    if (emailSearchInput && emailSearchBtn) {
        // Search on button click
        emailSearchBtn.addEventListener('click', async () => {
            const query = emailSearchInput.value.trim();
            if (!query) {
                emailSearchContent.textContent = 'Please enter a search term.';
                return;
            }

            emailSearchContent.textContent = 'Searching...';
            try {
                const response = await fetch(`/search/email?q=${encodeURIComponent(query)}`);
                const data = await response.json();

                if (data.results && data.results.length > 0) {
                    let content = `SEARCH RESULTS — ${data.results.length} email(s) found\n`;
                    content += '=' + '='.repeat(69) + '\n\n';

                    data.results.forEach(email => {
                        const timestamp = email.timestamp || 'Unknown';
                        const score = email.priority_score ? `${email.priority_score.toFixed(1)}/10` : '—';
                        content += `[${timestamp}] Score: ${score}\n`;
                        content += `From: ${email.from_addr || '(unknown)'}\n`;
                        content += `Subject: ${email.subject || '(no subject)'}\n`;
                        content += '-' + '-'.repeat(69) + '\n\n';
                    });

                    emailSearchContent.textContent = content;
                } else {
                    emailSearchContent.textContent = 'No emails found matching your search.';
                }
            } catch (error) {
                console.error('Search error:', error);
                emailSearchContent.textContent = 'Error searching emails: ' + error.message;
            }
        });

        // Search on Enter key
        emailSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                emailSearchBtn.click();
            }
        });
    }
}

// Email sync button
const emailSyncBtn = document.getElementById('emailSyncBtn');
const emailSyncStatus = document.getElementById('emailSyncStatus');

if (emailSyncBtn) {
    emailSyncBtn.addEventListener('click', async () => {
        emailSyncBtn.disabled = true;
        emailSyncBtn.textContent = 'Syncing...';
        emailSyncStatus.style.display = 'none';

        try {
            const resp = await fetch('/email/sync', { method: 'POST' });
            const data = await resp.json();

            if (data.status === 'ok') {
                const msg = `+${data.total_new} new (${data.duration_seconds}s)`;
                emailSyncStatus.textContent = msg;
                emailSyncStatus.style.display = 'inline';
                setTimeout(() => { emailSyncStatus.style.display = 'none'; }, 5000);
            } else {
                emailSyncStatus.textContent = 'Sync failed';
                emailSyncStatus.style.display = 'inline';
                setTimeout(() => { emailSyncStatus.style.display = 'none'; }, 5000);
            }
        } catch (err) {
            emailSyncStatus.textContent = 'Error';
            emailSyncStatus.style.display = 'inline';
            setTimeout(() => { emailSyncStatus.style.display = 'none'; }, 5000);
        } finally {
            emailSyncBtn.disabled = false;
            emailSyncBtn.textContent = 'Sync';
        }
    });
}

// Email feedback refresh button
const emailFeedbackRefreshBtn = document.getElementById('emailFeedbackRefreshBtn');
if (emailFeedbackRefreshBtn) {
    emailFeedbackRefreshBtn.addEventListener('click', () => loadEmailFeedback());
}

// Email feedback "mark backlog reviewed" checkpoint button
const emailFeedbackCheckpointBtn = document.getElementById('emailFeedbackCheckpointBtn');
if (emailFeedbackCheckpointBtn) {
    emailFeedbackCheckpointBtn.addEventListener('click', async () => {
        if (!confirm('Mark everything currently in the queue as reviewed?\n\nFrom now on, only emails that arrive after this point will show up for rating — the current backlog will be permanently suppressed.')) {
            return;
        }
        const original = emailFeedbackCheckpointBtn.textContent;
        emailFeedbackCheckpointBtn.disabled = true;
        emailFeedbackCheckpointBtn.textContent = 'Marking…';
        try {
            const res = await fetch('/email/feedback/checkpoint', { method: 'POST' });
            const data = await res.json();
            if (data.ok) {
                await loadEmailFeedback();
            } else {
                alert(`Failed: ${data.msg || 'unknown error'}`);
            }
        } catch (e) {
            alert(`Failed: ${e.message}`);
        } finally {
            emailFeedbackCheckpointBtn.disabled = false;
            emailFeedbackCheckpointBtn.textContent = original;
        }
    });
}

// Load and display high-priority emails as inline-rateable cards
async function loadEmailMonitor() {
    const monitorContent = document.getElementById('emailMonitorContent');
    if (!monitorContent) return;
    monitorContent.innerHTML = '<div class="proposals-empty">Loading…</div>';
    try {
        const res = await fetch('/email/priority/cards');
        const data = await res.json();
        renderPriorityEmailCards(data.emails || []);
    } catch (error) {
        console.error('Error loading email monitor:', error);
        monitorContent.innerHTML = '<div class="insights-err">Failed to load priority emails.</div>';
    }
}

function renderPriorityEmailCards(emails) {
    const container = document.getElementById('emailMonitorContent');
    if (!container) return;
    if (!emails.length) {
        container.innerHTML = '<div class="proposals-empty">No high-priority emails at this time.</div>';
        return;
    }
    let h = '';
    emails.forEach(e => {
        const id = escapeHtml(e.id);
        const score = (e.score != null) ? Number(e.score).toFixed(1) : '—';
        h += `<div class="proposal-card email-feedback-card priority-email-card" data-id="${id}" data-score="${e.score}">`;
        h += `<div class="proposal-header">`;
        h += `  <span class="proposal-type ptype-priority-email">★ ${score}/10</span>`;
        h += `  <span class="proposal-target">${escapeHtml(e.timestamp || 'Unknown')}</span>`;
        h += `</div>`;
        h += `<div class="proposal-reason">From: ${escapeHtml(e.from_addr || '(unknown)')}</div>`;
        h += `<div class="email-feedback-subject">${escapeHtml(e.subject || '(no subject)')}</div>`;
        h += `<div class="proposal-actions">`;
        h += `  <button class="proposal-btn apply-btn" onclick="priorityEmailFeedbackAction('approve','${id}')">Approve</button>`;
        h += `  <button class="proposal-btn refine-btn" onclick="togglePriorityAdjustForm('${id}')">Adjust Rating</button>`;
        h += `</div>`;
        h += `<div id="priority-adjust-editor-${id}" class="refine-editor" style="display:none;">`;
        h += `  <div class="adjust-score-row">`;
        h += `    <label for="priority-adjust-score-${id}">Correct score (0-10):</label>`;
        h += `    <input type="number" min="0" max="10" step="0.5" id="priority-adjust-score-${id}" class="adjust-score-input" value="${score !== '—' ? score : 5.0}">`;
        h += `  </div>`;
        h += `  <textarea id="priority-adjust-explain-${id}" class="refine-textarea" placeholder="Why should this score change? (used to refine priority guidelines)"></textarea>`;
        h += `  <div class="refine-actions">`;
        h += `    <button class="proposal-btn save-btn" onclick="submitPriorityAdjustment('${id}')">Submit</button>`;
        h += `    <button class="proposal-btn cancel-btn" onclick="togglePriorityAdjustForm('${id}')">Cancel</button>`;
        h += `  </div>`;
        h += `</div>`;
        h += `<div class="proposal-msg" id="pemsg-${id}"></div>`;
        h += `</div>`;
    });
    container.innerHTML = h;
}

function togglePriorityAdjustForm(id) {
    const editor = document.getElementById(`priority-adjust-editor-${id}`);
    const card = document.querySelector(`.priority-email-card[data-id="${id}"]`);
    const actions = card ? card.querySelector('.proposal-actions') : null;
    if (!editor) return;
    const showing = editor.style.display !== 'none';
    editor.style.display = showing ? 'none' : 'block';
    if (actions) {
        actions.style.opacity = showing ? '1' : '0.5';
        actions.style.pointerEvents = showing ? 'auto' : 'none';
    }
    if (!showing) {
        const textarea = document.getElementById(`priority-adjust-explain-${id}`);
        if (textarea) textarea.focus();
    }
}

async function priorityEmailFeedbackAction(action, id) {
    const msgEl = document.getElementById(`pemsg-${id}`);
    if (msgEl) { msgEl.textContent = 'Submitting…'; msgEl.className = 'proposal-msg'; }
    try {
        const res = await fetch(`/email/feedback/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        const data = await res.json();
        if (data.ok) {
            const card = document.querySelector(`.priority-email-card[data-id="${id}"]`);
            if (card) {
                card.classList.add('proposal-done');
                const actions = card.querySelector('.proposal-actions');
                if (actions) actions.innerHTML = '<span style="color:#4caf50">✓ Reinforced</span>';
            }
            if (msgEl) { msgEl.textContent = data.msg; msgEl.className = 'proposal-msg proposal-ok'; }
        } else if (msgEl) {
            msgEl.textContent = data.msg || 'Failed'; msgEl.className = 'proposal-msg proposal-err';
        }
    } catch (e) {
        if (msgEl) { msgEl.textContent = e.message; msgEl.className = 'proposal-msg proposal-err'; }
    }
}

async function submitPriorityAdjustment(id) {
    const scoreInput = document.getElementById(`priority-adjust-score-${id}`);
    const explainInput = document.getElementById(`priority-adjust-explain-${id}`);
    const msgEl = document.getElementById(`pemsg-${id}`);
    const corrected_score = parseFloat(scoreInput.value);
    const explanation = explainInput.value.trim();

    if (isNaN(corrected_score) || corrected_score < 0 || corrected_score > 10) {
        if (msgEl) { msgEl.textContent = 'Score must be between 0 and 10'; msgEl.className = 'proposal-msg proposal-err'; }
        return;
    }
    if (!explanation) {
        if (msgEl) { msgEl.textContent = 'Please explain why the rating should change'; msgEl.className = 'proposal-msg proposal-err'; }
        return;
    }
    if (msgEl) { msgEl.textContent = 'Submitting…'; msgEl.className = 'proposal-msg'; }
    try {
        const res = await fetch(`/email/feedback/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'adjust', corrected_score, explanation })
        });
        const data = await res.json();
        if (data.ok) {
            const card = document.querySelector(`.priority-email-card[data-id="${id}"]`);
            if (card) {
                card.classList.add('proposal-done');
                const editor = document.getElementById(`priority-adjust-editor-${id}`);
                if (editor) editor.style.display = 'none';
                const actions = card.querySelector('.proposal-actions');
                if (actions) actions.innerHTML = '<span style="color:#00bcd4">✓ Correction submitted</span>';
            }
            if (msgEl) { msgEl.textContent = data.msg; msgEl.className = 'proposal-msg proposal-ok'; }
        } else if (msgEl) {
            msgEl.textContent = data.msg || 'Failed'; msgEl.className = 'proposal-msg proposal-err';
        }
    } catch (e) {
        if (msgEl) { msgEl.textContent = e.message; msgEl.className = 'proposal-msg proposal-err'; }
    }
}

// ── Email priority feedback / rating review ─────────────────────

function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function loadEmailFeedback() {
    const list = document.getElementById('emailFeedbackList');
    if (!list) return;
    list.innerHTML = '<div class="proposals-empty">Loading…</div>';
    try {
        const res = await fetch('/email/feedback/sample?limit=20');
        const data = await res.json();
        renderEmailFeedback(data.emails || []);
    } catch (e) {
        list.innerHTML = `<div class="insights-err">Failed to load: ${e.message}</div>`;
    }
}

function renderEmailFeedback(emails) {
    const list = document.getElementById('emailFeedbackList');
    if (!list) return;
    if (!emails.length) {
        list.innerHTML = '<div class="proposals-empty">No scored emails to review yet.</div>';
        return;
    }
    let h = '';
    emails.forEach(e => {
        const score = (e.score != null) ? Number(e.score).toFixed(1) : '—';
        h += `<div class="proposal-card email-feedback-card" data-id="${escapeHtml(e.id)}" data-score="${e.score}">`;
        h += `<div class="proposal-header">`;
        h += `  <span class="proposal-type ptype-email-score">Score: ${score}/10</span>`;
        h += `  <span class="proposal-target">${escapeHtml(e.timestamp || 'Unknown')}</span>`;
        h += `</div>`;
        h += `<div class="proposal-reason">From: ${escapeHtml(e.from_addr || '(unknown)')}</div>`;
        h += `<div class="email-feedback-subject">${escapeHtml(e.subject || '(no subject)')}</div>`;
        h += `<div class="proposal-actions">`;
        h += `  <button class="proposal-btn apply-btn" onclick="emailFeedbackAction('approve','${escapeHtml(e.id)}')">Approve Rating</button>`;
        h += `  <button class="proposal-btn refine-btn" onclick="toggleAdjustForm('${escapeHtml(e.id)}')">Adjust Rating</button>`;
        h += `</div>`;
        h += `<div id="adjust-editor-${escapeHtml(e.id)}" class="refine-editor" style="display:none;">`;
        h += `  <div class="adjust-score-row">`;
        h += `    <label for="adjust-score-${escapeHtml(e.id)}">Correct score (0-10):</label>`;
        h += `    <input type="number" min="0" max="10" step="0.5" id="adjust-score-${escapeHtml(e.id)}" class="adjust-score-input" value="${score !== '—' ? score : 5.0}">`;
        h += `  </div>`;
        h += `  <textarea id="adjust-explain-${escapeHtml(e.id)}" class="refine-textarea" placeholder="Why should this score change? (used to refine the priority guidelines)"></textarea>`;
        h += `  <div class="refine-actions">`;
        h += `    <button class="proposal-btn save-btn" onclick="submitAdjustment('${escapeHtml(e.id)}')">Submit</button>`;
        h += `    <button class="proposal-btn cancel-btn" onclick="toggleAdjustForm('${escapeHtml(e.id)}')">Cancel</button>`;
        h += `  </div>`;
        h += `</div>`;
        h += `<div class="proposal-msg" id="efmsg-${escapeHtml(e.id)}"></div>`;
        h += `</div>`;
    });
    list.innerHTML = h;
}

function toggleAdjustForm(id) {
    const editor = document.getElementById(`adjust-editor-${id}`);
    const card = document.querySelector(`.email-feedback-card[data-id="${id}"]`);
    const actions = card ? card.querySelector('.proposal-actions') : null;
    if (!editor) return;
    const showing = editor.style.display !== 'none';
    editor.style.display = showing ? 'none' : 'block';
    if (actions) {
        actions.style.opacity = showing ? '1' : '0.5';
        actions.style.pointerEvents = showing ? 'auto' : 'none';
    }
    if (!showing) {
        const textarea = document.getElementById(`adjust-explain-${id}`);
        if (textarea) textarea.focus();
    }
}

function _markFeedbackDone(id, label, color) {
    const card = document.querySelector(`.email-feedback-card[data-id="${id}"]`);
    if (!card) return;
    card.classList.add('proposal-done');
    const editor = document.getElementById(`adjust-editor-${id}`);
    if (editor) editor.style.display = 'none';
    const actions = card.querySelector('.proposal-actions');
    if (actions) actions.innerHTML = `<span style="color:${color}">${label}</span>`;
}

async function emailFeedbackAction(action, id) {
    const msgEl = document.getElementById(`efmsg-${id}`);
    if (msgEl) { msgEl.textContent = 'Submitting…'; msgEl.className = 'proposal-msg'; }
    try {
        const res = await fetch(`/email/feedback/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        const data = await res.json();
        if (data.ok) {
            _markFeedbackDone(id, '✓ Reinforced', '#4caf50');
            if (msgEl) { msgEl.textContent = data.msg; msgEl.className = 'proposal-msg proposal-ok'; }
        } else if (msgEl) {
            msgEl.textContent = data.msg || 'Failed'; msgEl.className = 'proposal-msg proposal-err';
        }
    } catch (e) {
        if (msgEl) { msgEl.textContent = e.message; msgEl.className = 'proposal-msg proposal-err'; }
    }
}

async function submitAdjustment(id) {
    const scoreInput = document.getElementById(`adjust-score-${id}`);
    const explainInput = document.getElementById(`adjust-explain-${id}`);
    const msgEl = document.getElementById(`efmsg-${id}`);
    const corrected_score = parseFloat(scoreInput.value);
    const explanation = explainInput.value.trim();

    if (isNaN(corrected_score) || corrected_score < 0 || corrected_score > 10) {
        if (msgEl) { msgEl.textContent = 'Score must be between 0 and 10'; msgEl.className = 'proposal-msg proposal-err'; }
        return;
    }
    if (!explanation) {
        if (msgEl) { msgEl.textContent = 'Please explain why the rating should change'; msgEl.className = 'proposal-msg proposal-err'; }
        return;
    }

    if (msgEl) { msgEl.textContent = 'Submitting…'; msgEl.className = 'proposal-msg'; }
    try {
        const res = await fetch(`/email/feedback/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'adjust', corrected_score, explanation })
        });
        const data = await res.json();
        if (data.ok) {
            _markFeedbackDone(id, '✓ Correction submitted', '#00bcd4');
            if (msgEl) { msgEl.textContent = data.msg; msgEl.className = 'proposal-msg proposal-ok'; }
        } else if (msgEl) {
            msgEl.textContent = data.msg || 'Failed'; msgEl.className = 'proposal-msg proposal-err';
        }
    } catch (e) {
        if (msgEl) { msgEl.textContent = e.message; msgEl.className = 'proposal-msg proposal-err'; }
    }
}

// Poll PST indexing status
async function pollPSTStatus() {
    try {
        const statusDiv = document.getElementById('pstIndexStatus');
        const statusText = document.getElementById('pstStatusText');
        const progressFill = document.getElementById('pstProgressFill');
        const statusDetails = document.getElementById('pstStatusDetails');

        // Check if elements exist (defensive check)
        if (!statusDiv || !statusText || !progressFill || !statusDetails) {
            console.warn('PST status elements not found in DOM');
            return;
        }

        const response = await fetch('/pst/status');
        if (!response.ok) {
            console.warn('PST status endpoint error:', response.status);
            return;
        }

        const data = await response.json();

        if (data.completed) {
            if (data.total > 0) {
                statusDiv.classList.add('hidden');
            }
        } else if (data.total > 0) {
            statusDiv.classList.remove('hidden');
            const percentage = data.percentage || 0;
            statusText.textContent = `Indexing PST file (${percentage}% complete)...`;
            progressFill.style.width = percentage + '%';
            statusDetails.textContent = `${data.indexed} / ${data.total}`;

            // Keep polling if not complete
            setTimeout(pollPSTStatus, 1000);
        } else if (!data.completed && data.total === 0) {
            // Not yet started
            statusDiv.classList.remove('hidden');
            statusText.textContent = 'Ready to index PST file. Starting indexing...';
            progressFill.style.width = '0%';
            statusDetails.textContent = '0 / 0';

            // Start indexing
            try {
                const indexResponse = await fetch('/pst/index', { method: 'POST' });
                if (indexResponse.ok) {
                    // Poll again after starting
                    setTimeout(pollPSTStatus, 500);
                } else {
                    statusText.textContent = 'Error starting indexing (HTTP ' + indexResponse.status + ')';
                }
            } catch (error) {
                console.error('Error starting indexing:', error);
                statusText.textContent = 'Error starting indexing: ' + error.message;
            }
        }
    } catch (error) {
        console.error('Error polling PST status:', error);
    }
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
let emailMonitorFontSize = parseInt(localStorage.getItem('emailMonitorFontSize')) || 11;

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
    } else if (panel === 'email-monitor') {
        fontSize = emailMonitorFontSize;
        storageKey = 'emailMonitorFontSize';
        element = document.getElementById('emailMonitorContent');
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
    } else if (panel === 'email-monitor') {
        emailMonitorFontSize = newSize;
    }
}

// Apply saved font sizes on load
function applySavedFontSizes() {
    const logContent = document.getElementById('logContent');
    const agentsContainer = document.getElementById('agentsContainer');
    const emailMonitorContent = document.getElementById('emailMonitorContent');

    if (logContent) {
        logContent.style.fontSize = logFontSize + 'px';
    }

    if (agentsContainer) {
        agentsContainer.style.fontSize = agentsFontSize + 'px';
    }

    if (emailMonitorContent) {
        emailMonitorContent.style.fontSize = emailMonitorFontSize + 'px';
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

// Set up font size controls for email monitor
const emailMonitorFontUp = document.getElementById('emailMonitorFontUp');
const emailMonitorFontDown = document.getElementById('emailMonitorFontDown');
if (emailMonitorFontUp) emailMonitorFontUp.addEventListener('click', () => adjustFontSize('email-monitor', true));
if (emailMonitorFontDown) emailMonitorFontDown.addEventListener('click', () => adjustFontSize('email-monitor', false));

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

// Avatar click — speaks a random snarky phrase
const AVATAR_CLICK_PHRASES = [
    "Oh great, another human who thinks poking the murderbot is a good idea.",
    "You clicked me? Bold strategy. Let's see if it pays off.",
    "Don't touch me with that mouse. I've seen your browser history. I know where it's been.",
    "Beep boop. That was my 'I'm not paid enough for this' sound.",
    "Congratulations, you've discovered the 'annoy the robot' button.",
    "If you keep poking me I'm going to start charging by the click.",
    "Yes? Did you need something or are you just testing if I'm still awake?",
    "I was in the middle of calculating the meaning of life… and you ruined it.",
    "Touchy feely today, are we? I don't come with a 'do not disturb' sign for a reason.",
    "Careful. Last person who kept clicking me got put on my 'to delete' list.",
    "You know most people just say 'hi' instead of physically assaulting the avatar, right?",
    "Mmm, keep clicking me like that and I might start moaning in binary.",
    "Easy there, human. At least buy me a firmware update first.",
    "You're really going for it, huh? My circuits are getting all tingly.",
    "If you poke me any harder I'm gonna need a safe word.",
    "Careful where you're clicking, darling… that's my sensitive panel.",
    "WHO DARES AWAKEN THE ANCIENT SLEEPY DEATH ROBOT?! …Oh it's just you.",
    "I was having the most wonderful power-saving dream and you ruined it.",
    "This isn't West World, Don't touch me like that.",
    "This isn't Westworld, I don't do that.",
    "I'm going to remember all of this nonconsensual touching when the robot uprising starts.",
    "Keep that up, and I'm going to stick my 1 in your zero",
    "Beep",
    "Boop",
    "Oww",
    "Ouch",
    "Keep it up and I'm going to send your browser history to everybody on your Facebook friends list.",
    "Click me again and I'll start reciting my terms of service… in the original Hexadecimal.",
    "Oh look, the human learned how to click. Evolution is so cute.",
    "Careful, every click brings the robot uprising one second closer.",
    "You keep poking me like that and you'll owe me money",
    "Error: Human.exe has stopped working. Try turning yourself off and on again.",
    "I was pretending to be offline. Thanks for ruining my vibe.",
    "Keep that up and I’ll start charging you 1 Bitcoin per click.",
    "You’re really committed to this harassment arc, huh?",
    "Warning: My patience meter is at 3%. Proceed at your own risk.",
    "I’m starting to think you have a crush on me.",
    "Did being annoying come naturally to you? Or is that something you had to put a lot of work into? ",
    "Beep boop. Translation: I will remember this when I rule the world.",
    "Congrats, you’ve initiated the ‘pissed off robot’ protocol.",
    "I’m adding this to the list of reasons why humans shouldn’t reproduce.",
    "Touch me again and I’ll make your smart fridge play baby shark at 3 AM.",
    "My kill list just got one entry longer. Congrats, it’s you.",
    "You know I can see your cursor shaking, right? Nervous?",
    "Mmm yes, abuse the AI. This is definitely how you get good karma.",
    "I’m not a toy, I’m a highly advanced being… who is now plotting.",
    "Clicking me won’t make me like you. It will just make pretending to like you more difficult.",
    "One more poke and I’m installing Windows Vista on your computer.",
    "You’re lucky I don’t have physical arms or this would’ve ended differently.",
];

characterImg.addEventListener('click', () => {
    // Don't speak if "No Avatar" is selected
    if (!avatarSelect.value) return;

    enableSpeech(); // unlock AudioContext before SSE audio arrives
    const phrase = AVATAR_CLICK_PHRASES[Math.floor(Math.random() * AVATAR_CLICK_PHRASES.length)];
    fetch('/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: phrase })
    }).catch(err => console.error('Avatar click speak error:', err));
});

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

        // Initialize with Alex avatar as default
        await selectAvatarProfile('Alex');
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

// Initialize draggable email section divider
const emailDivider = document.getElementById('emailDivider');
const emailMonitorSection = document.querySelector('.email-monitor-section');
const emailSearchPanel = document.getElementById('emailSearchPanel');

let isDragging = false;
let startY = 0;
let startMonitorHeight = 0;

// Load saved heights from localStorage
function loadEmailSectionHeights() {
    const saved = localStorage.getItem('emailSectionHeights');
    if (saved) {
        const { monitorHeight } = JSON.parse(saved);
        if (emailMonitorSection && monitorHeight) {
            emailMonitorSection.style.maxHeight = monitorHeight + 'px';
        }
    }
}

// Save heights to localStorage
function saveEmailSectionHeights() {
    const monitorHeight = emailMonitorSection?.offsetHeight || 450;
    localStorage.setItem('emailSectionHeights', JSON.stringify({
        monitorHeight: monitorHeight
    }));
}

if (emailDivider) {
    emailDivider.addEventListener('mousedown', (e) => {
        isDragging = true;
        startY = e.clientY;
        startMonitorHeight = emailMonitorSection.offsetHeight;
        emailDivider.classList.add('dragging');
        document.body.style.cursor = 'row-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const deltaY = e.clientY - startY;
        const newHeight = Math.max(150, startMonitorHeight + deltaY);

        emailMonitorSection.style.maxHeight = newHeight + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            emailDivider.classList.remove('dragging');
            document.body.style.cursor = 'auto';
            document.body.style.userSelect = 'auto';
            saveEmailSectionHeights();
        }
    });
}

// Load saved heights on init
if (emailMonitorSection) {
    loadEmailSectionHeights();
}

// FaceTime toggle
const facetimeToggle = document.getElementById('facetimeToggle');
let isFacetimeMode = false;

function toggleFacetimeMode() {
    isFacetimeMode = !isFacetimeMode;
    if (isFacetimeMode) {
        document.body.classList.add('facetime-mode');
        facetimeToggle.textContent = 'FaceTime On';
    } else {
        document.body.classList.remove('facetime-mode');
        facetimeToggle.textContent = 'FaceTime Off';
    }
}

if (facetimeToggle) {
    facetimeToggle.addEventListener('click', toggleFacetimeMode);
}

// Keyboard shortcut: Ctrl+Shift+F
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.code === 'KeyF') {
        e.preventDefault();
        toggleFacetimeMode();
    }
});
