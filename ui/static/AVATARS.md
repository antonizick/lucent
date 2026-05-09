# Avatar System — Lucent Voice Box

## Overview

The Lucent Voice Box now supports dynamic avatar selection with state-based animations. The system automatically discovers avatars from the folder structure and switches between different animated states based on speaking activity.

## Directory Structure

Avatars are organized in `/static/avatars/`:

```
static/
├── noavatar.jpg                          (placeholder when no avatar selected)
└── avatars/
    ├── Emma/
    │   ├── Talking/                      (images shown while TTS is speaking)
    │   ├── Idle/                         (images shown within 2 min of last speech)
    │   ├── Waiting/                      (images shown 2-8 min after speech)
    │   └── Bored/                        (images shown 8+ min after speech)
    └── Other Avatar/
        ├── Talking/
        ├── Idle/
        ├── Waiting/
        └── Bored/
```

## States & Transitions

| State | Condition | Duration |
|-------|-----------|----------|
| **Talking** | TTS is actively speaking | Variable (while speaking) |
| **Idle** | Within 2 minutes of last speech | 0-2 min |
| **Waiting** | 2-8 minutes since last speech | 2-8 min |
| **Bored** | 8+ minutes since last speech | 8+ min |

State transitions are automatic and smooth. Timers reset whenever the avatar starts speaking.

## Image Requirements

- **Format:** PNG, JPG, GIF, or WebP
- **Dimensions:** Recommended 280×380px (matches character panel viewport)
- **Quantity:** Any number (0 or more per state)
  - The system randomly selects images from the available pool on each animation frame
  - Empty folders fall back gracefully (to Idle → Waiting → Bored → no avatar)

## Animation Behavior

### Talking State
- Cycles through images in `Talking/` folder
- Timing: 80-160ms per frame (natural mouth movement)
- Runs while TTS is actively outputting audio

### Idle/Waiting/Bored States
- Cycles through images in the respective state folder
- Timing: Changes expression every 3 seconds
- 15% chance of rapid "flicker burst" (quick multi-frame animation)
- Smooth transitions when state changes

## Adding a New Avatar

1. Create a new folder: `static/avatars/YourAvatarName/`
2. Create four subfolders: `Talking/`, `Idle/`, `Waiting/`, `Bored/`
3. Add image files to each state folder (PNG/JPG/GIF/WebP)
4. Restart the Voice Box server (or refresh the page)
5. The new avatar will automatically appear in the dropdown

Example:
```bash
mkdir -p static/avatars/Luna/{Talking,Idle,Waiting,Bored}
cp my_luna_images/*.png static/avatars/Luna/Idle/
cp my_luna_speaking/*.png static/avatars/Luna/Talking/
# (repeat for Waiting/ and Bored/)
```

## Technical Details

### Image Discovery & Caching
- Avatar folders are discovered on startup via `/api/avatars` endpoint
- Image lists are cached per avatar/state combination
- Images are preloaded (but not rendered until needed) for instant state transitions
- No code changes required when adding avatars or images

### Fallback Behavior
- If a state folder is empty or missing, the system falls back: Idle → Waiting → Bored → noavatar.jpg
- If an avatar folder is deleted, "No Avatar" mode displays noavatar.jpg (static image, no animation)
- Graceful error handling throughout

### Performance
- Image preloading is efficient and non-blocking
- State transitions trigger image cycling (not reloading)
- Caching prevents redundant API calls when switching between avatars

## API Endpoints

- `GET /api/avatars` — List available avatars
- `GET /api/avatars/{avatar}/images?state={state}` — List images for avatar/state

## Example Usage

To use an avatar:
1. Open Lucent Voice Box
2. Select an avatar from the dropdown in the header (left of the activity log button)
3. Speak a message via the Voice Box
4. Watch the avatar animate through Talking → Idle → Waiting → Bored states as needed
5. Selection is saved to localStorage and persists across sessions

## Existing Avatars

**Emma** — Sample avatar with full state coverage, populated from the original frame set.
