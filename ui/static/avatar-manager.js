// Avatar management system with dynamic folder discovery and image caching

class AvatarManager {
  constructor() {
    this.avatars = [];
    this.imageCache = new Map(); // avatar -> state -> [images]
    this.preloadCache = new Map(); // avatar -> state -> [Image objects]
  }

  async discoverAvatars() {
    try {
      const response = await fetch('/api/avatars');
      const data = await response.json();
      this.avatars = data.avatars || [];
      return this.avatars;
    } catch (error) {
      console.error('Failed to discover avatars:', error);
      this.avatars = [];
      return [];
    }
  }

  async getStateImages(avatar, state) {
    const cacheKey = `${avatar}:${state}`;
    if (this.imageCache.has(cacheKey)) {
      return this.imageCache.get(cacheKey);
    }

    try {
      const response = await fetch(`/api/avatars/${avatar}/images?state=${state}`);
      const data = await response.json();
      const images = data.images || [];
      this.imageCache.set(cacheKey, images);
      return images;
    } catch (error) {
      console.error(`Failed to load images for ${avatar}/${state}:`, error);
      return [];
    }
  }

  preloadStateImages(avatar, state, images) {
    const cacheKey = `${avatar}:${state}`;
    if (this.preloadCache.has(cacheKey)) {
      return this.preloadCache.get(cacheKey);
    }

    const preloaded = images.map(img => {
      const preloadImg = new Image();
      preloadImg.src = img;
      return preloadImg;
    });

    this.preloadCache.set(cacheKey, preloaded);
    return preloaded;
  }

  getRandomImage(images) {
    if (!images || images.length === 0) return null;
    return images[Math.floor(Math.random() * images.length)];
  }
}

window.AvatarManager = AvatarManager;
