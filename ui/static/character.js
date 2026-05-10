// Character animator with multi-avatar support and state machine (Talking, Idle, Waiting, Bored)

const AVATAR_STATES = {
  TALKING: 'Talking',
  IDLE: 'Idle',
  WAITING: 'Waiting',
  BORED: 'Bored'
};

const STATE_THRESHOLDS = {
  IDLE: 2 * 60 * 1000,      // 2 minutes
  WAITING: 8 * 60 * 1000    // 8 minutes
};

const ANIMATION_TIMING = {
  speak: { min: 80, max: 160 },        // mouth movement during talking
  idle: 3000,                           // idle expression change interval
  bored: { min: 1500, max: 3500 },     // slow bored state animation
  stateCheck: 5000                      // check state transitions every 5 seconds
};

class CharacterAnimator {
  constructor(imgEl, panelEl, avatarManager) {
    this.img = imgEl;
    this.panel = panelEl;
    this.avatarManager = avatarManager;
    this.currentAvatar = null;
    this.currentState = AVATAR_STATES.IDLE;
    this.speaking = false;
    this.lastSpeakTime = Date.now();

    this.speakTimer = null;
    this.stateTimer = null;
    this.idleTimer = null;

    this.currentStateImages = [];
    this.currentIdleFrame = null;

    this._startStateCheckLoop();
  }

  async setAvatar(avatar) {
    if (this.currentAvatar === avatar) return;
    this.currentAvatar = avatar;

    if (!avatar) {
      this._showNoAvatar();
      return;
    }

    // Preload all state images for the new avatar
    const states = [AVATAR_STATES.TALKING, AVATAR_STATES.IDLE, AVATAR_STATES.WAITING, AVATAR_STATES.BORED];
    for (const state of states) {
      const images = await this.avatarManager.getStateImages(avatar, state);
      if (images.length > 0) {
        this.avatarManager.preloadStateImages(avatar, state, images);
      }
    }

    // Update to current state
    await this._transitionToState(this.currentState);
  }

  startSpeaking() {
    this.speaking = true;
    this.lastSpeakTime = Date.now();
    this.panel.classList.add('speaking');
    clearTimeout(this.speakTimer);
    clearTimeout(this.idleTimer);

    this._updateState(AVATAR_STATES.TALKING);
  }

  async stopSpeaking() {
    this.speaking = false;
    this.panel.classList.remove('speaking');
    clearTimeout(this.speakTimer);
    this.lastSpeakTime = Date.now();

    // Immediately transition to idle state instead of waiting for state check loop
    await this._transitionToState(AVATAR_STATES.IDLE);
  }

  async _transitionToState(newState) {
    if (this.currentState === newState && this.currentStateImages.length > 0) {
      return; // Already in this state with images loaded
    }

    this.currentState = newState;

    if (!this.currentAvatar) {
      this._showNoAvatar();
      return;
    }

    const images = await this.avatarManager.getStateImages(this.currentAvatar, newState);

    if (images.length === 0) {
      // Fallback chain: Idle -> Waiting -> Bored -> no avatar
      if (newState !== AVATAR_STATES.IDLE) {
        await this._transitionToState(AVATAR_STATES.IDLE);
      } else if (newState !== AVATAR_STATES.WAITING) {
        await this._transitionToState(AVATAR_STATES.WAITING);
      } else if (newState !== AVATAR_STATES.BORED) {
        await this._transitionToState(AVATAR_STATES.BORED);
      } else {
        this._showNoAvatar();
      }
      return;
    }

    this.currentStateImages = images;
    this.currentIdleFrame = null;

    if (newState === AVATAR_STATES.TALKING && this.speaking) {
      this._runTalkingCycle();
    } else {
      this._runIdleCycle();
    }
  }

  _updateState(newState) {
    if (this.currentState !== newState) {
      this._transitionToState(newState);
    }
  }

  _determineState() {
    if (this.speaking) {
      return AVATAR_STATES.TALKING;
    }

    const timeSinceSpeech = Date.now() - this.lastSpeakTime;

    if (timeSinceSpeech < STATE_THRESHOLDS.IDLE) {
      return AVATAR_STATES.IDLE;
    } else if (timeSinceSpeech < STATE_THRESHOLDS.WAITING) {
      return AVATAR_STATES.WAITING;
    } else {
      return AVATAR_STATES.BORED;
    }
  }

  _startStateCheckLoop() {
    const checkState = async () => {
      const newState = this._determineState();
      if (newState !== this.currentState) {
        await this._transitionToState(newState);
      }
      this.stateTimer = setTimeout(checkState, ANIMATION_TIMING.stateCheck);
    };
    checkState();
  }

  _runTalkingCycle() {
    if (!this.speaking || !this.currentStateImages.length) return;

    const frame = this.avatarManager.getRandomImage(this.currentStateImages);
    if (frame) {
      this.img.src = frame;
    }

    const delay = ANIMATION_TIMING.speak.min +
                  Math.floor(Math.random() * (ANIMATION_TIMING.speak.max - ANIMATION_TIMING.speak.min));
    this.speakTimer = setTimeout(() => this._runTalkingCycle(), delay);
  }

  _runIdleCycle() {
    if (this.speaking || !this.currentStateImages.length) return;

    // Immediately show a frame
    const frame = this.avatarManager.getRandomImage(this.currentStateImages);
    if (frame) {
      this.img.src = frame;
    }

    const isBored = this.currentState === AVATAR_STATES.BORED;
    const holdTime = 300 + Math.floor(Math.random() * 300);

    this.idleTimer = setTimeout(() => {
      if (!this.speaking && this.currentStateImages.length > 0) {
        let delay;

        if (isBored) {
          // Slow animation in bored state: 1.5-3.5 seconds
          delay = ANIMATION_TIMING.bored.min +
                  Math.floor(Math.random() * (ANIMATION_TIMING.bored.max - ANIMATION_TIMING.bored.min));
        } else {
          // Normal idle or waiting state behavior
          const doFlicker = Math.random() < 0.15; // 15% chance of rapid flicker
          if (doFlicker) {
            this._runFlickerBurst();
            return;
          }
          delay = ANIMATION_TIMING.idle;
        }

        this.idleTimer = setTimeout(() => {
          if (!this.speaking && this.currentState === this._determineState()) {
            this._runIdleCycle();
          }
        }, delay);
      }
    }, holdTime);
  }

  _runFlickerBurst() {
    const flickerCount = 2 + Math.floor(Math.random() * 3);
    let flickerIndex = 0;

    const runFlicker = () => {
      if (this.speaking || flickerIndex >= flickerCount || !this.currentStateImages.length) {
        this._runIdleCycle();
        return;
      }

      const frame = this.avatarManager.getRandomImage(this.currentStateImages);
      if (frame) {
        this.img.src = frame;
      }

      flickerIndex++;
      const flickerDelay = 150 + Math.floor(Math.random() * 150);
      this.idleTimer = setTimeout(runFlicker, flickerDelay);
    };

    runFlicker();
  }

  _showNoAvatar() {
    this.img.src = '/static/noavatar.jpg';
    this.currentStateImages = [];
    clearTimeout(this.speakTimer);
    clearTimeout(this.idleTimer);
  }
}

window.CharacterAnimator = CharacterAnimator;
