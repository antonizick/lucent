# Palettes

Seven ready-made palettes, back-ported from AIVU's deck renderer
(`idea/AIVU/backend/app/deck_themes.py`) where they ship with an automated
WCAG contrast test. Paste one over the **Colors** block in `template.html`'s
`:root` — nothing else in the file changes.

`template.html`'s built-in default is still ChessLoop's dark/gold; these are
alternatives, not a replacement. Pick one when Nick names a mood ("warmer",
"light for a projector", "quieter") or when the deck's subject already has a
palette worth matching.

## Choosing

| Palette | Mode | Reach for it when |
|---|---|---|
| **Midnight** | dark | Technical/academic default. Near-black, cool blue. |
| **Ember** | dark | Warm charcoal + copper. Softer at night, less clinical. |
| **Forest** | dark | Deep green/sage. Quiet, low-contrast, calm subject matter. |
| **Parchment** | light | **The one to pick for a projector or a printed handout.** |
| **Mist** | light | Cool blue-grey + deep teal. Crisp, clinical, data-heavy. |
| **Linen** | light | Soft warm grey + terracotta. Gentler than Parchment. |
| **Sage** | light | Pale green-grey + moss. Low-glare for a long sitting. |

**Light vs. dark is decided by the room, not by taste.** A dark deck on a
weak projector in a lit room is unreadable; a light deck on a laptop at night
is glare. Ask which one it is if it isn't obvious.

---

## Dark

### Midnight (AIVU academic dark)
```css
    --bg: #0a0a0a;
    --card-bg: #17171b;
    --card-border: #26262c;
    --text: #c0c0c0;
    --text-dim: #8a8a92;
    --accent-primary: #00bfff;
    --accent-primary-bright: #7fdcff;
    --accent-secondary: #5bc0de;
    --accent-success: #4f9d69;
    --accent-warn: #c1666b;
    --shadow: 0 20px 60px rgba(0,0,0,0.5);
    --glow: 0 0 24px rgba(0,191,255,0.45);
    --font-heading: Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

### Ember
```css
    --bg: #100c0a;
    --card-bg: #1c1613;
    --card-border: #302620;
    --text: #d6cbc2;
    --text-dim: #9a8b80;
    --accent-primary: #d08b4f;
    --accent-primary-bright: #f0b57e;
    --accent-secondary: #c2766a;
    --accent-success: #93a35f;
    --accent-warn: #c9564f;
    --shadow: 0 20px 60px rgba(0,0,0,0.55);
    --glow: 0 0 24px rgba(208,139,79,0.4);
    --font-heading: Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

### Forest
```css
    --bg: #090f0c;
    --card-bg: #141d18;
    --card-border: #223029;
    --text: #c3cec6;
    --text-dim: #7f9187;
    --accent-primary: #5fae82;
    --accent-primary-bright: #96d9b0;
    --accent-secondary: #8fb0c0;
    --accent-success: #b0bf72;
    --accent-warn: #c98f6a;
    --shadow: 0 20px 60px rgba(0,0,0,0.5);
    --glow: 0 0 24px rgba(95,174,130,0.4);
    --font-heading: Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

## Light

> **`accent-primary-bright` must be *darker* than `accent-primary` on a light
> palette.** It colours the headings, and "bright" means "more prominent
> against *this* background" — which inverts with the background. Getting it
> backwards is how you end up with pale headings nobody can read on a
> projector. This is the single easiest rule here to invert by reflex.
>
> Light palettes also set `--glow: none` — a halo behind dark ink on paper
> reads as a printing fault, not an effect.

### Parchment
```css
    --bg: #f4f1ea;
    --card-bg: #fbf9f4;
    --card-border: #ddd6c8;
    --text: #2f2b25;
    --text-dim: #6d675c;
    --accent-primary: #2f5d7c;
    --accent-primary-bright: #1e4560;
    --accent-secondary: #7a5c3e;
    --accent-success: #4a6b4f;
    --accent-warn: #a1443c;
    --shadow: 0 18px 44px rgba(70,60,42,0.16);
    --glow: none;
    --font-heading: Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

### Mist
```css
    --bg: #eef2f5;
    --card-bg: #f9fbfc;
    --card-border: #ccd7de;
    --text: #1e2830;
    --text-dim: #596773;
    --accent-primary: #286b78;
    --accent-primary-bright: #164a55;
    --accent-secondary: #4c6b85;
    --accent-success: #3f6b52;
    --accent-warn: #9d4038;
    --shadow: 0 18px 44px rgba(35,55,70,0.14);
    --glow: none;
    --font-heading: Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

### Linen
```css
    --bg: #f6f3ef;
    --card-bg: #fdfbf8;
    --card-border: #e0d8cd;
    --text: #2b2724;
    --text-dim: #665e55;
    --accent-primary: #9c5539;
    --accent-primary-bright: #743a24;
    --accent-secondary: #6a6250;
    --accent-success: #4f6b4a;
    --accent-warn: #a03f36;
    --shadow: 0 18px 44px rgba(70,58,45,0.14);
    --glow: none;
    --font-heading: Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

### Sage
```css
    --bg: #eef2ec;
    --card-bg: #f8faf6;
    --card-border: #cfd9c9;
    --text: #212820;
    --text-dim: #586154;
    --accent-primary: #416d48;
    --accent-primary-bright: #2b4d32;
    --accent-secondary: #5a6f7c;
    --accent-success: #4b6b3f;
    --accent-warn: #9a4238;
    --shadow: 0 18px 44px rgba(45,60,42,0.14);
    --glow: none;
    --font-heading: Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

---

## Custom palettes — check the contrast, don't eyeball it

Any hand-mixed palette (a brand colour, a screenshot's colours, "make it
purple") gets run through this before the deck is built. The seven above
already pass; a new one has no such guarantee, and "looks fine on my monitor"
has never survived a projector.

Targets, matching AIVU's `test_deck_render.py`:

| Pair | Ratio |
|---|---|
| `text` on `bg`, and `text` on `card-bg` | **≥ 7:1** (AAA body text) |
| `accent-primary-bright` on `bg`/`card-bg` (headings) | ≥ 4.5:1 |
| `text-dim` on `bg`/`card-bg` (muted text, captions, `.cite`) | ≥ 4.5:1 |
| `accent-primary` on `bg` (rules, bullets, borders — never text) | ≥ 3:1 |

```python
# contrast.py — paste-and-run, no dependencies
def lum(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(c * 2 for c in h)
    c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

P = {  # <- the palette under test
    "bg": "#0a0a0a", "card-bg": "#17171b", "text": "#c0c0c0",
    "text-dim": "#8a8a92", "accent-primary": "#00bfff",
    "accent-primary-bright": "#7fdcff",
}
CHECKS = [("text", 7.0), ("text-dim", 4.5), ("accent-primary-bright", 4.5),
          ("accent-primary", 3.0)]
for surface in ("bg", "card-bg"):
    for key, need in CHECKS:
        r = ratio(P[key], P[surface])
        print(f"{'ok ' if r >= need else 'FAIL'} {key} on {surface}: {r:.2f} (need {need})")

# Light palettes only: headings must be darker than the plain accent.
if lum(P["bg"]) > 0.5:
    assert lum(P["accent-primary-bright"]) < lum(P["accent-primary"]), \
        "light palette: accent-primary-bright must be DARKER than accent-primary"
```

A failing pair gets fixed before the deck is built, not noted as a caveat
afterwards.
