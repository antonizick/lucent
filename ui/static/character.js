// Frame-based character animator for Lucent's Voice Box UI

const IDLE_FRAMES = [
  'idle_neutral', 'idle_left', 'idle_right',
  'idle_up', 'idle_amused', 'idle_skeptical'
];
const SPEAK_FRAMES = ['speak_closed', 'speak_small', 'speak_mid', 'speak_wide'];
const FRAME_PATH = '/static/frames/';

class CharacterAnimator {
  constructor(imgEl, panelEl) {
    this.img = imgEl;
    this.panel = panelEl;
    this.speaking = false;
    this.speakTimer = null;
    this.idleTimer = null;
    this.currentIdleFrame = 'idle_neutral';
    this.frameCache = new Map();
    this._preloadFrames();
    this._scheduleIdleBehavior();
  }

  _preloadFrames() {
    const allFrames = [...IDLE_FRAMES, ...SPEAK_FRAMES];
    allFrames.forEach(frame => {
      const img = new Image();
      img.src = `${FRAME_PATH}${frame}.png`;
      this.frameCache.set(frame, img);
    });
  }

  _setFrame(name) {
    this.img.src = `${FRAME_PATH}${name}.png`;
  }

  startSpeaking() {
    this.speaking = true;
    this.panel.classList.add('speaking');
    clearTimeout(this.idleTimer);
    this._runSpeakCycle();
  }

  stopSpeaking() {
    this.speaking = false;
    this.panel.classList.remove('speaking');
    clearTimeout(this.speakTimer);
    this._setFrame('idle_neutral');
    this._scheduleIdleBehavior();
  }

  _runSpeakCycle() {
    if (!this.speaking) return;
    // Weight frames: more time on mid/small, less on extremes
    const weights = [2, 3, 3, 1]; // closed, small, mid, wide
    const pool = SPEAK_FRAMES.flatMap((f, i) => Array(weights[i]).fill(f));
    const frame = pool[Math.floor(Math.random() * pool.length)];
    this._setFrame(frame);
    // Random interval 80–160ms for natural mouth movement
    const delay = 80 + Math.floor(Math.random() * 80);
    this.speakTimer = setTimeout(() => this._runSpeakCycle(), delay);
  }

  _scheduleIdleBehavior() {
    if (this.speaking) return;
    // Decide whether to do normal behavior or quick flicker burst
    const doFlicker = Math.random() < 0.15; // 15% chance of flicker burst

    if (doFlicker) {
      // Quick flicker burst: rapidly cycle through 2-4 random frames
      const flickerCount = 2 + Math.floor(Math.random() * 3);
      let flickerIndex = 0;

      const runFlicker = () => {
        if (this.speaking || flickerIndex >= flickerCount) {
          // After burst, return to neutral and resume normal scheduling
          this.currentIdleFrame = 'idle_neutral';
          this._setFrame('idle_neutral');
          this._scheduleIdleBehavior();
          return;
        }

        const choices = IDLE_FRAMES.filter(f => f !== this.currentIdleFrame);
        const frame = choices[Math.floor(Math.random() * choices.length)];
        this.currentIdleFrame = frame;
        this._setFrame(frame);

        flickerIndex++;
        // Quick interval: 150–300ms for rapid flickering
        const flickerDelay = 150 + Math.floor(Math.random() * 150);
        this.idleTimer = setTimeout(runFlicker, flickerDelay);
      };

      runFlicker();
    } else {
      // Normal behavior: change expression every 3 seconds (no random slowdown)
      const delay = 3000;
      this.idleTimer = setTimeout(() => {
        if (this.speaking) return;
        // Pick a frame different from current
        const choices = IDLE_FRAMES.filter(f => f !== this.currentIdleFrame);
        const frame = choices[Math.floor(Math.random() * choices.length)];
        this.currentIdleFrame = frame;
        this._setFrame(frame);
        // Brief pause: 300–600ms before next expression
        const holdTime = 300 + Math.floor(Math.random() * 300);
        this.idleTimer = setTimeout(() => {
          if (!this.speaking) {
            this.currentIdleFrame = 'idle_neutral';
            this._setFrame('idle_neutral');
          }
          this._scheduleIdleBehavior();
        }, holdTime);
      }, delay);
    }
  }
}

// Export for use in app.js
window.CharacterAnimator = CharacterAnimator;
