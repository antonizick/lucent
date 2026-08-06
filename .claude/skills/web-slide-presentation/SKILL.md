---
name: web-slide-presentation
description: >-
  Turn a brief, an outline, or a fully-dictated script into a scroll-snap HTML
  slide presentation with auto-playing per-slide narration — the ChessLoop
  pattern (presentation/chessloop/index.html), Nick's gold-standard template
  for this format. Use when the deliverable is a presentation viewed by
  clicking/scrolling through a browser page. Not a static .pptx (use
  slide-deck), not a narrated MP4 (use video-presentation), and NOT built with
  HyperFrames — do not route this to /hyperframes or its workflows. Triggers:
  "web slide presentation", "HTML deck", "browser presentation", "like
  ChessLoop", "scrollable slides", "web slides". Nick may supply screenshots/
  graphics and dictate the outline, per-slide content, and image placement
  directly, or hand off a brief and let this skill draft the outline for
  review.
---

# Web-Slide Presentation

Hand-authored static HTML/CSS/JS — no build step, no framework, no
HyperFrames. One `index.html` per project, scroll-snap sections, vanilla JS
for navigation and audio sync. This is deliberately a different, simpler
pipeline than `video-presentation`/`slide-deck`; see "Format routing" in
`video-presentation`'s SKILL.md for how the three get disambiguated.

**Output location:** `presentation/<project-slug>/` at the repo root —
matches ChessLoop exactly. Not under `idea/Presentation` (that project owns
the video/pptx pipeline only).

## Hard requirements — non-negotiable on every deck

These came from a line-by-line audit of ChessLoop with Nick. Every one of
these must be true before a deck is considered done:

1. **Colors as CSS custom properties**, declared once at `:root`, easy names
   (`--bg`, `--accent-primary`, etc.) — changing the palette is editing that
   one block, nothing else. See `template.html`'s THEME block.
2. **Title slide (slide 00):** subtle metadata block upper-left — project
   title, `Author: <name>`, date. Small, muted, **left-aligned** (explicit
   `text-align: left` on `.metadata` — it sits inside `.title-slide`, which
   sets `text-align: center` for the hero content, and without the override
   the metadata lines center relative to each other instead of flush-aligning),
   not competing with the h1.
3. **Title slide content:** the project name plus plain-language navigation
   instructions for the viewer (buttons / arrows / PgUp-PgDn / space / click).
4. **Navigation controls, lower-right:** prev/next buttons + an auto-advance
   toggle, all operable by button click, keyboard (arrows, space, PgUp/PgDn),
   or clicking anywhere on the slide.
5. **Nav buttons resize for mobile** — 44×44px desktop, 88×88px under
   `max-width: 640px` (needs the viewport meta tag to actually apply).
6. **Audio auto-sync:** loading a slide stops whatever's playing and starts
   that slide's narration (`audio/slide.NN.mp3`) automatically. Slide 1's
   narration also autoplays on initial page load (muted-then-unmute trick to
   satisfy browser autoplay policy).
7. **Slide numbers, upper-right, subtle** — `NN / total`. Auto-computed by JS
   from slide count, never hand-typed (hand-typed numbers in ChessLoop were a
   real maintenance foot-gun — fixed in `template.html`).
8. **Subtle entrance animation per slide** — text fades in, cards/screenshots
   slide in — triggered once via `IntersectionObserver` when the slide first
   scrolls into view. Timing must be **tunable from a few variables at the
   top of the file**, not scattered magic numbers.
9. **Font sizes** — `template.html`'s h1/h2/subtitle/lede/card-heading/list/
   tag sizes (plus their mobile media-query overrides) are the baseline, and
   the template is the single source of truth for the exact numbers; new
   decks inherit them by starting from it. Don't shrink them for a new
   project unless asked.

   There is also a **large ("projector") scale**, built for the 2026-07-19
   AIVU pass and living in `presentation/AIVU/indexLG.html`. Same markup,
   bigger type — reach for it when the deck will be shown on a projector or
   a TV rather than read on a laptop. Overriding these five values on top of
   the template is the whole change:

   ```css
   section.slide { padding: 3rem 6vw; }
   h1          { font-size: clamp(3.6rem, 8.5vw, 6.4rem); line-height: 1.05; }
   h2          { font-size: clamp(2.9rem, 6vw, 4.3rem);   line-height: 1.08; }
   .subtitle   { font-size: clamp(1.7rem, 3vw, 2.2rem);   line-height: 1.2; }
   .lede       { font-size: 1.7rem; line-height: 1.35; }
   .card h3    { font-size: 1.65rem; }
   .cards      { gap: 0.9rem; }
   .card       { padding: 1rem 1.3rem; }
   ```

   Ask which it is if the deck's viewing context isn't obvious; the two
   scales are not interchangeable and the wrong one is visibly wrong.
10. **`.lede-list` needs a width cap on image-paired slides** — on any
    `section.slide:has(.shot-wrap)`, `.cards` has `max-width: 45%` so it
    doesn't run under the absolutely-positioned image, but `.lede-list`
    didn't get the same treatment and its bullet text would wrap full-width,
    right under the screenshot. Fixed in `template.html` with a matching
    `section.slide:has(.shot-wrap) > .lede-list { max-width: 45%; }` rule
    (and the existing 768px breakpoint already resets it to 100% on mobile —
    keep that pairing intact if this block ever moves).
11. **Layout variety** — no single layout carries more than **60%** of a
    deck's teaching slides (see "Layout variety" below). This is a hard
    requirement, not a preference: it's the one thing that separates a deck
    that teaches from a deck that reads as one slide repeated.
12. **Imagery density** — decks are visual by default, not text by default:
    - **At least 1 in 3 slides carries a visual** (photo, screenshot, or
      diagram).
    - **Never more than 3 consecutive slides without one.** This is the rule
      that actually matters — a deck can hit the ratio and still have a dead
      stretch in the middle, which is exactly where an audience checks out.
    - **The hero and the closing get a photo backdrop** unless the deck is
      deliberately text-only. `template.html` ships both blocks with `.bleed`
      already in place, so this is opt-out.

    Imagery is not decoration to add if there's time — it is part of the
    first draft. Plan it in Stage 1, resolve it in Stage 1b, and check it in
    Stage 5. See "Photography" below.

## Layout variety — the shape of the slide matches the shape of the idea

This section is the 2026-07-29 back-port from AIVU's deck renderer
(`idea/AIVU/backend/app/deck_template.py`), which hit this problem at scale
and solved it with mechanisms rather than good intentions.

**The failure it fixes.** The original template shipped five layouts, of
which only two (`content-list`, `cards-grid`) fit an arbitrary teaching
slide. Given that vocabulary, every slide came out a bulleted list and the
deck read as one slide repeated with different words. Restraint on the
layout set was the cause, not a safeguard.

### Vocabulary

| Layout | Use it for |
|---|---|
| `content-list` | The default: loose points that belong together. |
| `cards-grid` | 2–4 parallel things as a taxonomy. |
| `cards-image` | Anything with a screenshot or diagram to show. |
| `video-half` | Anything where the thing being shown *moves*: a demo, a walkthrough, a recorded talk. See "Video slides" below. |
| `compare` | "A versus B", before/after, do-this-not-that. 2–3 panels, optional good/bad tone. |
| `steps` | An ordered procedure — the reader must see it's a sequence. |
| `definition` | One term the viewer has to retain, at term size. |
| `statement` | One principle alone on the slide, poster size. |
| `quote` | A source's own words, verbatim. |
| `stat` | 1–3 figures that matter, at figure size. |
| `timeline` | Events, versions, or phases in order. |
| `code` | A listing beside what it means — never the listing alone. |
| `image-full` | Photo as backdrop, words on top. Section openers, emotional beats. |
| `image-half` | Photo owns one half, bleeding off the edge. Add `flip` for left. |
| `image-band` | Cropped strip as a chapter divider. |
| `image-grid` | 2–4 tiles forced to one aspect ratio. |
| `title` · `closing` | Bookends. Never used for a teaching slide. |

Every one of these is a copyable TYPE block in `template.html`, is driven
entirely by CSS custom properties, and needs no image and no font the deck
doesn't already carry — so any of them works on any slide of any deck.

### Three mechanisms that keep variety honest

1. **Pick the layout from the content, not from habit.** When drafting the
   outline, name the *shape* of each section's idea first — sequence, term,
   trade-off, figure, principle, listing, taxonomy, chronology — then take
   the layout with that name. Reaching for `content-list` because it's the
   default is the failure mode; a genuinely loose set of points is the only
   thing that earns it.
2. **Measure the finished outline** (`outline.json`, before building):
   no layout above 60% of teaching slides, counted across `slides[]` with
   `type` not in `title`/`closing`, minimum 4 teaching slides before the
   rule applies. Over 60% → re-shape the offenders, don't ship it.

   ```python
   import json, collections
   s = json.load(open("outline.json"))["slides"]
   k = [x["type"] for x in s if x["type"] not in ("title", "closing")]
   if len(k) >= 4:
       t, n = collections.Counter(k).most_common(1)[0]
       assert n / len(k) <= 0.6, f"layout monotony: {n}/{len(k)} slides are {t!r}"
   ```
3. **Alternate `content-list` between stacked and split.** Even an honestly
   list-shaped deck shouldn't look like one slide repeated. Use the plain
   `content-list` block for odd-numbered list slides and the `.slide.split`
   variant (heading in its own left rail) for even ones. Same content,
   different presentation — it cannot lose anything.

### Content caps per layout

These are the points past which a layout stops being readable at
presentation distance. Ported from AIVU's `lint_spec`; treat them as limits,
not targets.

| Cap | Value |
|---|---|
| Bullets per slide / points per card / points per compare column | 5 |
| Words per bullet | 12 |
| Cards | 6 (animation stagger is defined up to 6) |
| Compare columns | 3 |
| Steps | 6 |
| Stats | 3 |
| Timeline events | 5 |
| Code lines | 18 |
| `statement` words | 30 |
| `quote` words | 45 |

Over a cap is a rewrite signal — split the slide or cut the words. It is
never a reason to shrink the type.

## Video slides — `video-half`

Added 2026-08-06. Same shape as `cards-image` — context on the left, the visual
on the right — with a real player instead of a still. The wrapper deliberately
keeps the `shot-wrap` class so it inherits every positioning, entrance-animation
and mobile-reflow rule already proven on the image case; only the video-specific
CSS is new. Reach for it when the subject *moves* and a screenshot would lose
the point: a product demo, a UI walkthrough, a recorded piece to camera.

### Non-negotiables

1. **Never `autoplay`.** The clip waits for a deliberate press. A slide that
   starts talking the moment it scrolls into view fights its own narration and
   startles the viewer.
2. **Always `controls`.** Start, stop, scrub, rewatch — all of it, native.
3. **Always a `poster`.** Without one Chromium paints a black rectangle, and
   that black rectangle is what the video export screenshots. Generate it from
   the clip itself at build time — never ship a video slide without one:
   ```bash
   ffmpeg -y -ss 3 -i presentation/<slug>/video/clip.mp4 \
     -frames:v 1 -q:v 2 presentation/<slug>/images/clip-poster.jpg
   ```
   Pick the timestamp by *looking* at the frame, not by taking `-ss 3` on
   faith — a poster landing on a transition, a blank screen, or a mid-blink
   is the first thing an audience sees of the clip.
4. **Files live in `presentation/<slug>/video/`**, referenced relatively
   (`src="video/clip.mp4"`), exactly like `images/`. Never hotlink, never use
   an absolute filesystem path.
5. **Keep the left rail short** — four points at most. The clip is the content;
   the bullets say what to watch for and why it's here. If the left side needs
   more, the clip isn't carrying the slide and this is the wrong layout.
6. **One video per slide.** The exporter rejects a second one, and two players
   on one slide is a decision the viewer shouldn't have to make.
7. **Match the clip's loudness to the narration** — see below. A clip that
   makes the viewer reach for the volume knob is a broken slide.

### Loudness — one target, shared by construction

A supplied recording is never at the deck's level. The first one measured
**-29.96 LUFS** against narration at **-18 LUFS**: a 12 dB step, audible the
instant the clip started.

This is not a judgement call and not a manual step. `scripts/loudness.py` owns
the constants (`TARGET_LUFS = -18.0`, `TARGET_TP = -1.5`, `TOLERANCE_LU = 2.0`);
`narrate.py` imports it to normalise every segment it renders, and
`export_deck_video.py` imports it to audit what it's about to encode. **One
number, two consumers, no drift.** Normalise every clip when you wire it in:

```bash
python3 idea/Presentation/scripts/loudness.py normalize presentation/<slug>/video/clip.mp4
```

That is the whole procedure. It measures, applies two-pass `loudnorm` in place,
**copies the video stream untouched**, and prints the before/after level plus
the video-packet MD5 both sides of the operation to prove the picture never
moved. To check any set of files against the house target:

```bash
python3 idea/Presentation/scripts/loudness.py measure \
  presentation/<slug>/audio/*.mp3 presentation/<slug>/video/*.mp4
```

Exit code 0 means everything is inside tolerance.

**Why not just turn the clip up.** That clip peaked at -3.25 dBTP while sounding
12 dB quiet — perceived loudness and peak level are different things. Flat gain
of +12 dB would have clipped by nearly 9 dB. `loudnorm` carries a limiter, which
is why it can raise perceived level at all.

**Normalise the file, not the export.** The browser plays the file on disk, so
fixing levels only inside the exporter would leave the live deck quiet and the
MP4 correct. The exporter therefore reports and warns; it never repairs.

Expect `normalization_type: dynamic` on a screen recording — a source with 15+
LU of range cannot be lifted 12 dB linearly without clipping, so the filter
compresses. Correct treatment for speech from a room mic, but it does lift the
quiet passages, so **listen to the result**; the tooling measures, it doesn't
have ears.

### Behaviour, and why it differs from every other slide

On a video slide the **clip** decides when the deck moves on, not the narration.
Three coupled rules, all in `template.html`'s script:

- **Pressing play pauses the slide narration.** Two voices at once is never the
  intent, and the narration exists to introduce the clip anyway.
- **Auto-advance waits for the clip to end**, not the narration. Without this, a
  20-second narration in front of a two-minute clip scrolls the deck away
  mid-sentence — the bug this rule exists to prevent.
- **A clip nobody starts never auto-advances.** Deliberate: this is the one
  slide that asks the viewer to do something, so it waits for them. Say so in
  the narration ("press play when you're ready") — an unattended deck parked on
  a video slide is otherwise indistinguishable from a stall.

Leaving the slide pauses the clip but keeps its position, so coming back
resumes rather than restarting. The click-anywhere-to-advance handler excludes
the player, or a mis-click on the scrub bar would jump the deck.

### Narration for a video slide

Write it **short** — one or two sentences that frame the clip and hand over.
Its job is to say what the viewer is about to see and why it's in the deck, not
to compete with it. Then stop talking.

### It counts toward imagery density

A `video-half` slide satisfies hard requirement 12 the same way a screenshot
does. The Stage 5 density check counts it (`shot-wrap` matches either).

## Photography — Openverse imagery

Added 2026-07-30. `idea/Presentation/scripts/imagery.py` finds a CC-licensed
photo for a slide, vets it with a local vision model, and freezes it into the
deck's `images/` with the credit recorded. The four `image-*` layouts above
are built to make a stranger's photo look like it was commissioned.

### The one rule that decides whether this works

**Editorial, never explanatory.** These images carry *tone*; the text carries
the *argument*. Measured 2026-07-30: retrieval works for concrete nouns and
collapses for abstract concepts — "firewall" returns rack photography,
"first-match-wins evaluation order" returns nothing usable. So:

- **Search the noun in the scene you want, not the idea the slide teaches.**
  A slide about rule evaluation order gets a search for `server room`, not
  `rule evaluation`.
- Anything that has to *explain* a concept is a diagram. Use
  `diagram-builder` / Sketchlab. A photo will never do that job.

### Stage 1b — plan the imagery with the outline, not after it

Imagery gets skipped when it's a separate later step, so it isn't one. As soon
as the outline exists, write an image plan beside it and resolve the whole set
in one command:

```jsonc
// images.json — one entry per slide that needs a visual
[
  {"name": "hero",      "query": "library reading room bookshelves",
   "topic": "A personal virtual university built around depth of study"},
  {"name": "challenge", "query": "empty lecture hall seats",
   "topic": "Traditional learning is one-size-fits-all with poor retention"},
  {"name": "closing",   "query": "sunrise over rolling hills",
   "topic": "An aspirational closing suggesting progress and mastery ahead"}
]
```

```bash
cd idea/Presentation
python3 scripts/imagery.py batch images.json \
  --out-dir ../../presentation/<slug>/images
```

One failure doesn't abort the run — the deck gets everything that resolved and
the failures are listed to retry with a better query. **Then look at all of
them together** (a contact sheet is quickest) before wiring any in; judging
them as a set is how you catch the one that doesn't belong.

### Resolve a single image

```bash
python3 scripts/imagery.py resolve "server room datacenter" \
  --topic "Where firewall rules actually run" \
  --out-dir presentation/<slug>/images --name hero --tint '#d4af37'
```

`--topic` is what the slide teaches — it drives the vision gate, which rejects
off-topic images, watermarks, embedded text, and busy compositions. Measured:
~30 s per image including 2–3 rejections. Other subcommands: `search` (list
candidates, download nothing), `credits <dir> [--short]` (print the ledger).

Three gates, cheapest first: deterministic (width/aspect) → vision model
(`qwen3.6:27b`) → **you**. The file lands on disk; look at it before shipping.
If Ollama is down the vision gate is skipped loudly and the deterministic pick
stands — it's an accelerator, not the only safeguard.

### Non-negotiables

1. **Never hotlink.** `imagery.py` downloads and freezes the file into
   `images/`. A remote `src` rots, and fetching it hands this deck's own URL
   to the host in the `Referer` header — the same leak class as the citation
   links.
2. **Always carry the credit.** CC-BY *requires* it. Put
   `imagery.py credits <dir> --short` output (`Photo: Creator / CC BY-SA 2.0`)
   in the slide's `.cite` footer. The full Openverse attribution paragraph is
   too long for a footer — it wraps across the slide and collides with body
   text; keep it in `images/credits.json`.
3. **Tint whenever a deck uses more than two photos.** `class="tint"` on the
   `.bleed`/`.img-tile`/`.img-band-strip` grayscales and re-tones to
   `--accent-primary`. This single treatment is what makes unrelated stock
   photography read as one deck. `imagery.py --tint '#hex'` bakes the same
   effect into the file for the `.pptx` and video pipelines, which have no CSS
   filters — use it so all three outputs match.
4. **Resolution.** Openverse is Flickr-dominated and Flickr's linked file caps
   at 1024px. `imagery.py` defaults to `--source wikimedia,rawpixel` (median
   2288–4000px) and falls back to all sources with a warning when a subject is
   too niche. A 1024px file is fine for `image-half`/`image-grid`/`image-band`
   and soft on `image-full` — prefer a hi-res source for full-bleed.

### Layout notes learned building these

- `section.slide.has-bleed` raises its children above the backdrop, but
  `.cite` and `.slide-num` are **already absolutely positioned** and are
  excluded from that rule. Forcing `position: relative` on them drops the
  credit onto the body text and moves the slide number to the left margin —
  both were real bugs, both are fixed in `template.html`. Keep the exclusion
  if that block ever moves.
- `.bleed` can go under `statement`, `quote` and `title` slides too — use the
  `center` scrim variant so the type doesn't land on a bright edge. It's the
  highest-impact photo slide in the set; use it once in a deck, not five times.
- Photography fades in; it never slides. A backdrop that moves pulls the eye
  off the words it exists to support.

### Citations

Any slide can carry a `.cite` footer (source label, optionally linked).
`rel="noopener noreferrer"` on that link is **not optional**: a real leak
was found in AIVU's decks where `noopener` alone handed the deck's own URL
to the third-party site in the `Referer` header. If a deck will live at a
non-public URL, also add `<meta name="referrer" content="no-referrer">` to
its `<head>`.

## Stage 0 — Intake (what Nick provides)

Everything here is optional and can be mixed freely per project:

- **Screenshots/graphics** — drop image files anywhere Claude can read them
  (or point at an existing folder). If Nick says which image goes on which
  slide, use that assignment as-is. If images are supplied with no placement
  given, propose an assignment (matched by filename/content to the relevant
  slide topic) and confirm before building.
- **Video clips** — drop an MP4 anywhere Claude can read it and say which slide
  it belongs on. It becomes a `video-half` slide (see "Video slides"). **Watch
  the clip before wiring it in** — sample frames across its length and, if it
  has speech, transcribe it. A file named for one thing and containing another
  is not a hypothetical: it happened on the first deck this layout was built
  for, and only frame-sampling caught it.
- **Outline/content dictation** — Nick can hand over anything from a one-line
  brief ("build a deck for X, here's the product") to a fully written,
  slide-by-slide script with exact wording. Use exactly what's dictated
  verbatim; only draft/fill what wasn't specified.
- **Narration voice direction** — Nick can specify engine, gender/accent, and
  speed per project. See "Voice selection" under Stage 3 for what's actually
  available right now (real, verified options — not aspirational).
- **Nothing at all** — given just a project name and a pointer at the
  codebase/docs, draft the full outline (structure, copy, image placement)
  and present it for review before building.

Regardless of mode, always show the drafted (or confirmed) outline and full
narration script back to Nick before generating audio — mirrors
`video-presentation`'s "nothing renders blind" rule. Nick edits by saying
what to change; don't regenerate audio for slides whose text didn't change.

## Pipeline

```
Stage 0  intake            screenshots + dictated/brief content (above)
Stage 1  author outline.json
Stage 2  draft narration text per slide → show Nick for review
Stage 3  narrate.py → WAV → ffmpeg → audio/slide.NN.mp3
Stage 4  render index.html from template.html + outline.json
Stage 5  verify (see below) — do not report done off a clean exit code
Stage 6  export to MP4 (optional) — export_deck_video.py
```

## Stage 1 — outline.json

```json
{
  "project": "ChessLoop",
  "author": "Nick Antonizick",
  "date": "18 July 2026",
  "deploy_url": "https://example.ts.net:8443/",
  "voice_engine": "xtts",
  "voice_reference": "SteveGibson.wav",
  "voice_name": "en_GB-cori-high",
  "narration_speed": 1.25,
  "voice_speed": 0.7,
  "animation_speed": "default",
  "theme": { "accent-primary": "#d4af37" },
  "slides": [
    { "type": "title", "instructions": "Use the navigation buttons below..." },
    { "type": "title", "tagline": "...", "lede": "...", "tags": ["Teach", "Practice"], "narration": "..." },
    { "type": "content-list", "heading": "...", "subtitle": "...",
      "items": [{"label": "Teach", "detail": "..."}], "narration": "..." },
    { "type": "cards-grid", "heading": "...", "subtitle": "...",
      "cards": [{"title": "...", "points": ["..."]}], "narration": "..." },
    { "type": "cards-image", "heading": "...", "subtitle": "...",
      "cards": [{"title": "...", "points": ["..."]}],
      "image": "images/screenshot.png", "image_alt": "...", "narration": "..." },
    { "type": "video-half", "heading": "...", "subtitle": "...",
      "items": ["what to watch for"],
      "video": "video/clip.mp4", "poster": "images/clip-poster.jpg",
      "video_alt": "...", "video_aspect": "16 / 9", "narration": "..." },

    { "type": "compare", "heading": "...", "subtitle": "...",
      "columns": [{"title": "...", "tone": "bad", "points": ["..."]},
                  {"title": "...", "tone": "good", "points": ["..."]}], "narration": "..." },
    { "type": "steps", "heading": "...", "subtitle": "...",
      "steps": [{"title": "...", "detail": "..."}], "narration": "..." },
    { "type": "definition", "heading": "...", "term": "...", "definition": "...",
      "items": ["optional note"], "narration": "..." },
    { "type": "statement", "heading": "OPTIONAL KICKER", "statement": "...",
      "note": "...", "narration": "..." },
    { "type": "quote", "quote": "...", "attribution": "...", "narration": "..." },
    { "type": "stat", "heading": "...", "subtitle": "...",
      "stats": [{"value": "94%", "label": "..."}], "narration": "..." },
    { "type": "timeline", "heading": "...", "subtitle": "...",
      "events": [{"when": "2024", "title": "...", "detail": "..."}], "narration": "..." },
    { "type": "code", "heading": "...", "subtitle": "...", "language": "python",
      "code": "…", "items": ["what to notice"], "narration": "..." },

    { "type": "image-full", "heading": "...", "subtitle": "...", "items": ["..."],
      "image": "images/hero.jpg", "image_alt": "...", "tint": true,
      "credit": "Photo: Creator / CC BY-SA 2.0", "narration": "..." },
    { "type": "image-half", "heading": "...", "flip": false,
      "image": "images/side.jpg", "credit": "...", "narration": "..." },
    { "type": "image-band", "heading": "...", "image": "images/band.jpg",
      "credit": "...", "narration": "..." },
    { "type": "image-grid", "heading": "...",
      "tiles": [{"image": "images/a.jpg", "caption": "..."}],
      "credit": "...", "narration": "..." },

    { "type": "closing", "closing_line": "...", "closing_body": "...", "narration": "..." }
  ]
}
```

Any slide may also carry `"citation": {"label": "...", "url": "..."}` (renders
as the `.cite` footer) and `"audio": "audio/whatever.mp3"` (overrides the
positional naming; use `"silent": true` for a slide with no narration).

`tone` on a compare column is `good` / `bad` / omitted — it swaps the column's
top rule and bullet glyph to ✓/✕. Omit both tones for a neutral comparison;
`good`/`bad` is an editorial claim, so only use it when the deck is actually
making one.

`theme` only needs the keys being overridden — anything omitted falls back to
`template.html`'s defaults (ChessLoop's dark/gold palette). For a whole-deck
reskin, take one of the seven contrast-checked palettes in **`palettes.md`**
instead of mixing hexes by hand; that file also carries the runnable contrast
check any custom palette must pass. `animation_speed` is `fast` / `default` /
`slow`, mapped to the `--anim-*` duration variables (default = ChessLoop's
actual values; fast ≈ 0.6×, slow ≈ 1.6×).

`voice_engine` is `xtts` (default) or `piper`. For `xtts`, `voice_reference`
names one of the uploaded reference clips (see Stage 3's voice table).
For `piper`, `voice_name` is one of the installed models.

**`narration_speed` is the speed control — default `1.25`.** It maps to
`narrate.py --speed` and works on both engines (pitch-preserving time-stretch
applied after generation). Above 1.0 = faster, which is the direction Nick
wants; this is the opposite sense to Piper's `length_scale`, so don't confuse
the two. `voice_speed` still exists as Piper's own `length_scale` via
`/vox/speed` (below 1.0 = faster) — a synthesis-level alternative for Piper
only, and global voice-box state you must restore. Prefer `narration_speed`;
reach for `voice_speed` only if a Piper deck needs the pacing baked in at
synthesis time.

`narration` per slide is the spoken-cadence script text for that slide's
mp3 — if Nick dictated exact wording, use it verbatim; otherwise draft from
the slide's visible copy (bullets/cards condensed into natural spoken
sentences, not read verbatim off the screen).

## Stage 2 — Narration script review

Print the full per-slide narration script in one place before generating any
audio. Wait for a go/edit signal, then proceed.

## Stage 3 — Audio

`segments.json` is `[{"id": "01", "text": "..."}, ...]` — one entry per
slide, `id` zero-padded to match slide order.

### Voice selection

**Defaults are built into the tool, not asserted here.** `narrate.py` applies
all three of these on its own — you get them by running it, and you cannot get
them wrong by forgetting a flag. Set by Nick 2026-08-06:

| | Default | Opt out with | Why |
|---|---|---|---|
| Voice | XTTS, `JonRichardson.wav` | `--reference <other>` | The only reference uploaded; keep it until Nick finds a British female one (the standing ask) |
| Speed | **1.25×** | `--speed 1.0` | The as-generated pace reads as too slow in a deck |
| Loudness | **-18 LUFS** | `--no-normalize` | So narration matches embedded video, and every deck matches every other deck |

**Speed is a post-processing step, not an engine setting.** XTTS has no rate
parameter at all (`/api/generate` takes text, reference and language, nothing
else), and Piper's speed is *global voice-box state* that would have to be set
and restored around every batch. Doing it after generation with ffmpeg's
`atempo` phase-vocoder means one knob that works identically on both engines and
preserves pitch — 1.25 is 25% faster, not a chipmunk.

`audio_meta.json` durations are measured **after** retiming *and* normalisation,
so they always describe the file on disk — which both the deck and the video
exporter time slides off. It also records `speed` and `loudness_lufs` so a deck's
audio can be audited later without guessing how it was made.

`narrate.py` prints the loudness spread at the end and **warns** if any segment
missed the target by more than 2 LU. A clean exit is not the check; that line is.

Two real engines, each with different capabilities — pick based on what Nick
asks for, don't assume:

| Engine | Voices available today | Gender/accent | Speed control |
|---|---|---|---|
| **XTTS** (`idea/XTTS`, port 8300) | 1 uploaded reference clip: **`JonRichardson.wav`** — the deck default (verified 2026-08-06; `SteveGibson.wav` and `HonestTrailers2.wav` are gone) | Voice-cloned from whatever reference clip is used — no female reference uploaded yet | **Not exposed** — the `/api/generate` endpoint has no speed/rate param |
| **Piper** (voice box, port 8001) | 4 installed models: `en_GB-alan-medium` (UK male), `en_GB-northern_english_male-medium` (UK male), `en_GB-cori-high` (UK female), `en_GB-jenny_dioco-medium` (UK female) | Real gender/accent choice, but **UK English only** — no US voices installed | **Real per-call control** via `/vox/speed` (`length_scale`, range 0.25–4.0; below 1.0 = faster, above 1.0 = slower) |

Check `curl http://localhost:8001/vox/voices` and `curl http://localhost:8300/api/references`
before telling Nick what's available — voices get added over time, don't
recite this table from memory once it's stale.

- Nick wants a **specific gender/accent + speed** ("British female, speak
  quickly") → Piper is the only engine that can actually do this today.
- Nick wants **XTTS's cloned-voice quality** with no speed/gender ask →
  default XTTS engine is fine as-is.
- Nick wants a **voice XTTS doesn't have** (e.g. a specific female voice) →
  he can supply a short reference WAV and it uploads via
  `POST http://localhost:8300/api/upload` (multipart `file` field) — XTTS
  clones from any clip, no gender/accent restriction, just no speed knob.

**Piper voice/speed are global voice-box state — not per-request.** Changing
them for narration generation also changes Lucent's own spoken voice (the
`/speak` calls this same session makes) until changed back. Always:
1. `GET /vox/voices` → note `current`; read `speed` from the persisted config
   (or just remember it was 0.7 unless told otherwise).
2. `POST /vox/voice {"voice": "<name>"}` and `POST /vox/speed {"speed": <n>}`
   to the desired narration voice/speed.
3. Run the Piper batch (below).
4. `POST /vox/voice` and `POST /vox/speed` back to the values from step 1.
Do this restore even if the run fails partway — don't leave the voice box
talking in a narration voice after the fact.

### Generate

```bash
cd idea/Presentation
# 1.25x and -18 LUFS are the tool's own defaults — don't pass them, don't
# re-implement them, and don't "fix" the audio afterwards.
python3 scripts/narrate.py segments.json --engine xtts \
  --reference JonRichardson.wav --out-dir /tmp/<project>-audio
# or, after the voice switch above:
python3 scripts/narrate.py segments.json --engine piper --out-dir /tmp/<project>-audio
```

`narrate.py --engine auto` (default) tries XTTS first and falls back to
Piper only on failure — pass `--engine piper` explicitly when Nick wants a
deliberate Piper voice, otherwise XTTS's reference wins silently. Writes WAV
+ duration metadata per segment either way.

Convert to the mp3 naming convention the template's JS expects:

```bash
for f in /tmp/<project>-audio/*.wav; do
  n=$(basename "$f" .wav)
  ffmpeg -y -i "$f" -codec:a libmp3lame -qscale:a 4 "presentation/<project-slug>/audio/slide.${n}.mp3"
done
```

## Stage 4 — Build

1. Copy `template.html` to `presentation/<project-slug>/index.html`.
2. Set `<title>`, `{{PROJECT_NAME}}`, `{{AUTHOR}}`, `{{DATE}}`.
3. Apply any `theme` overrides into the `:root` block; apply
   `animation_speed` into the `--anim-*` vars.
4. For each `outline.json` slide entry, emit the matching `<section
   class="slide">` block from `template.html`'s TYPE comments — do not
   hand-invent new markup patterns; extend the template with a new TYPE block
   if a genuinely new layout is needed, and keep it CSS-var-driven like the
   rest.
5. Copy source images into `presentation/<project-slug>/images/`, referenced
   by filename only (relative `src="images/..."`, never absolute filesystem
   paths — a past HTML build used `encodeURIComponent()` on an absolute path,
   which percent-encodes `/` into garbage; keep paths relative and simple).
6. Copy source videos into `presentation/<project-slug>/video/` and generate a
   poster for each into `images/` (see "Video slides"). Same relative-path rule.
7. Leave every `<span class="slide-num"></span>` empty — the template's JS
   fills these in from slide count. Never hand-type slide numbers.

## Stage 5 — Verify (mandatory, not optional)

A clean build with no errors is not verification — a prior ChessLoop pass
shipped broken image paths and silently-discarded slide text while exiting 0.
Before reporting done:

- Serve the directory locally (`python3 -m http.server` from
  `presentation/<project-slug>/`) and actually load the page.
- Confirm slide count in the HTML matches audio file count in `audio/`
  (missing files fail silently — the audio player just won't play).
- Confirm every `<img src>` resolves to a real file in `images/`.
- Balanced `<section class="slide">` open/close tags.
- Click through at least the first few slides and one image slide; confirm
  audio fires, animation triggers, nav buttons and keyboard both work.
- **Run the monotony check** from "Layout variety" against `outline.json`,
  and eyeball one slide of every layout the deck actually uses — the
  variety layouts are newer than the list/card ones and get less mileage.
- **Run the imagery-density check** (hard requirement 12) against the built
  HTML. Ratio and longest dry run, both measured:

  ```python
  import re
  html = open("presentation/<slug>/index.html").read()
  secs = re.split(r'<section class="slide', html)[1:]
  has = [bool(re.search(r'class="[^"]*\b(bleed|shot-wrap|img-band-strip|img-grid)\b', s))
         for s in secs]
  run = best = 0
  for h in has:
      run = 0 if h else run + 1
      best = max(best, run)
  srcs = re.findall(r'<img src="([^"]+)"', html)
  dupes = {s for s in srcs if srcs.count(s) > 1}
  print(f"{sum(has)}/{len(has)} slides with a visual "
        f"({sum(has)/len(has):.0%}); longest run without: {best}; "
        f"{len(set(srcs))} distinct of {len(srcs)} images")
  assert sum(has) / len(has) >= 1/3, "under the 1-in-3 imagery floor"
  assert best <= 3, f"{best} consecutive slides with no visual"
  assert not dupes, f"same image reused across slides: {dupes}"
  ```

  **Every slide gets its own image, resolved from its own query.** Repeating
  one photo to hit the density floor is worse than having none — it reads as
  filler and tells the audience the pictures don't mean anything. The
  `{{IMAGE_FILENAME}}` placeholder appears in every photo TYPE block precisely
  because each copy gets a *different* file.
- If the palette isn't one of `palettes.md`'s seven, run its contrast
  script and clear every FAIL first.
- **Look at every photo.** The vision gate rejects watermarks and clutter; it
  does not have taste, and it cannot tell you an image is a cliché. Open the
  files in `images/` and confirm each earns its slide.
- Confirm every image slide has a credit line, and that
  `images/credits.json` has an entry per file. A missing credit on a CC-BY
  image is a licence violation, not a cosmetic gap.
- **On any `video-half` slide, check all six by hand** — the player is the one
  element that can look perfect in a screenshot and still be wrong:

  ```bash
  python3 - <<'PY'
  import re, pathlib
  deck = pathlib.Path("presentation/<slug>")
  raw = (deck / "index.html").read_text()
  # Strip style/script/comments first — the template DISCUSSES <video> in prose,
  # and a naive scan reports those mentions as attribute-less video tags.
  html = re.sub(r"<style\b.*?</style>|<script\b.*?</script>|<!--.*?-->", "", raw, flags=re.S)
  tags = re.findall(r"<video\b[^>]*>", html)
  assert tags, "no video slide found"
  for tag in tags:
      src = re.search(r'src="([^"]+)"', tag)
      poster = re.search(r'poster="([^"]+)"', tag)
      assert "controls" in tag, f"no controls: {tag}"
      assert "autoplay" not in tag, f"autoplay must never be set: {tag}"
      assert poster, f"no poster (export would capture a black frame): {tag}"
      for label, m in (("video", src), ("poster", poster)):
          assert m, f"no {label} on {tag}"
          assert (deck / m.group(1)).is_file(), f"missing {label} file: {m.group(1)}"
      print("ok:", src.group(1))
  PY
  ```

  Then, in the browser: play the clip and confirm the narration stops; let it
  run to the end and confirm the deck advances; click the scrub bar and confirm
  the deck does **not** advance; navigate away mid-clip and confirm the audio
  stops.

  **Confirm the clip and the narration are at the same level:**

  ```bash
  python3 idea/Presentation/scripts/loudness.py measure \
    presentation/<slug>/audio/*.mp3 presentation/<slug>/video/*.mp4
  ```

  Non-zero exit is a fail — go back to "Loudness" above. The exporter runs the
  same audit itself and prints the **narration-vs-clip step** in LU, which is
  the number a viewer actually experiences; anything over 2 LU is obvious.

  **Testing media over `python3 -m http.server` will mislead you.** It ignores
  HTTP Range requests, so Chromium cannot seek into a long clip and the
  "clip ends → deck advances" check fails for a reason that has nothing to do
  with the deck. Load the deck over `file://` for any test that seeks.

  One more trap when driving this with Playwright: on a video slide the `<h2>`
  box spans the full content width *underneath* the absolutely-positioned
  player (true of `cards-image` too), so a default centre-click on the heading
  lands on the video and times out. Click the text with an explicit
  `position={"x": 20, "y": 12}`.

## Stage 6 — Export the deck to MP4 (optional)

```bash
python3 idea/Presentation/scripts/export_deck_video.py presentation/<slug> \
  -o presentation/<slug>/<slug>.mp4
```

Screenshots every slide, holds it for exactly as long as its narration runs,
and — the reason this exists — **splices any embedded clip into the timeline**
at full length rather than freezing its poster. Requires playwright, ffmpeg,
ffprobe.

- **Interactive chrome is hidden automatically.** `.nav-controls` — the prev/next
  arrows and the "Auto Advance Slides" checkbox — is suppressed during capture:
  nobody can tick a checkbox in an MP4, and burning one into the lower-right of
  every frame reads as a mistake. Done with an injected style tag at capture
  time, so the live deck keeps its controls; nothing is removed from the deck.
  Slide numbers are deliberately *kept* — they still orient a video viewer.
  If a new interactive affordance is ever added to `template.html`, add it to
  `HIDE_FOR_CAPTURE` in the exporter at the same time.
- **It audits loudness before encoding** and prints the narration-vs-clip step.
  It reports rather than repairs — see "Loudness" — so a warning here means go
  and run `loudness.py normalize`, not shrug.
- **Always `--dry-run` first.** It prints the whole timeline (per-slide
  durations, where each clip lands, total runtime) plus the loudness audit, and
  encodes nothing. A wrong-looking total here is minutes saved.
- It reads slide→audio mapping by calling the deck's *own* `audioFor()` in the
  page, so `data-audio` / `data-silent` overrides can never drift out of sync
  with the export. A deck not built from `template.html` is rejected loudly.
- Silent slides (the slide-00 nav card) are held for `--silent-hold` seconds,
  default 4.
- Defaults to 1920×1080 / 30 fps / CRF 20; `--width/--height/--fps/--crf`
  override. Everything is normalised to one codec profile so the final concat
  is lossless.
- It warns if a video slide has no poster, and errors on a missing audio file,
  a missing clip, or more than one video on a slide. It also compares the
  finished file's duration against the printed timeline and warns on a
  mismatch — a dropped segment is otherwise silent.

Distinct from `idea/PATH/backend/app/video_export.py`, which does the same job
for PATH's *generated* lesson decks inside that app. If the video-splice
behaviour is ever wanted there too, both the `video-half` layout
(`deck_template.py`, `deck_spec.py`) and the splice step (`video_export.py`)
need it — they do not share code with this script.

## How to invoke this — for Nick

Just ask in plain language, e.g.:

> "Build a web-slide presentation for `<project>` like ChessLoop."
> "Make me a web deck for X — here's the outline: ..."
> "Web slides for X, use these screenshots: ... slide 3 gets the dashboard
> shot, slide 5 gets the settings shot."

Have ready (any subset — Claude fills gaps and confirms):

- Project name, one-line tagline, deployment/demo URL for the closing slide.
- Screenshots/graphics, with placement if you care which slide gets which.
- Outline or exact per-slide wording, as loose or as dictated as you want —
  a full script is fine, so is "just cover the main features."
- Voice direction if you care: gender, accent, speed ("British female,
  speak quickly"), or a specific XTTS reference clip. Say nothing and you
  get the XTTS default (male, normal pace). Ask "what voices are available"
  any time to get the live list rather than a stale answer.

Nothing else is required to start — Claude drafts, shows the outline and
narration script for review, then builds and verifies before calling it done.

### Ideal prompt — worked example

When you already have screenshots, a rough outline, and talking points
(not exact wording) ready, this is the complete, no-back-and-forth version:

> Build a web-slide presentation for AIVU, like ChessLoop.
>
> Screenshots are in `presentation/aivu/images/` — [use them wherever fits /
> here's placement: slide 3 = dashboard.png, slide 5 = api-flow.png].
>
> Rough outline:
> 1. What AIVU is
> 2. [...]
>
> Talking points per section (not exact wording — draft natural narration
> from these):
> - What AIVU is: [bullets]
> - [...]
>
> Tagline: "..."
> Deploy/demo URL: [url, or "not live yet — skip the closing link"]
> Voice: [XTTS default is fine / Piper British female normal speed / etc.]

Only the first line is actually required — everything else just removes a
round-trip. Drop screenshots directly into `presentation/<project-slug>/images/`
before starting (the eventual output location) so there's no separate
copy/placement step.

## Known limitations

- Layout set is fixed to the TYPE blocks in `template.html` (title,
  content-list ×2 variants, cards-grid, cards-image, video-half, compare,
  steps, definition, statement, quote, stat, timeline, code, closing). A genuinely
  new layout needs a new TYPE block added to the template — don't freehand
  one-off markup into a single deck. If you do add one, add it to AIVU's
  `deck_template.py` too, or the two vocabularies drift.
- `steps` numbers are typed by hand in the HTML (the template has no
  renderer to compute them). Keep them 1..N; AIVU's generated decks get
  this for free, hand-authored ones don't.
- No PDF/print export — this is a live browser artifact. For a narrated MP4
  see Stage 6; for a takeaway document that's `slide-deck` (.pptx).
- `video-half` exists only in `template.html`, not in PATH's `deck_template.py`
  — the two layout vocabularies are knowingly out of step on this one until
  PATH's generated decks actually need a video slide.
- The exporter re-encodes every embedded clip to the deck's codec profile, so
  a clip already at 1920×1080/30 still costs one encode pass. Fine at deck
  length; revisit with stream-copy fast-pathing if clips get long.
- `narrate.py`'s WAV → mp3 conversion is a manual `ffmpeg` loop in Stage 3,
  not wired into `narrate.py` itself — fine at current volume; revisit only
  if this becomes a recurring bottleneck.
