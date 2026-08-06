---
name: video-presentation
description: >-
  Turn a script, outline, or research brief into a narrated animated video (MP4)
  for the Presentation project (idea/Presentation) using HyperFrames. Use when
  the deliverable is a video with voice narration — it wires the local narration
  (XTTS/Piper via scripts/narrate.py) and diagram (scripts/diagram.py) pipelines
  into a HyperFrames composition and renders it. Not for static .pptx decks (use
  slide-deck) or standalone diagrams (use diagram-builder), and not a substitute
  for the HyperFrames domain skills — it sits on top of them and routes to them.
---

# Video Presentation

End-to-end methodology for the **narrated animated video** output of
`idea/Presentation`. Takes Nick's direction (a prompt, a doc, a research task,
or "just build it") → an MP4 with voice narration, animation, and embedded
diagrams.

**Entry point, not `/hyperframes`.** For a Presentation-project narrated-video
request, this skill *is* the router — it already ran (or IS) the intent
capture. Don't additionally run `/hyperframes`'s own intent layer or workflow
install (`/general-video`, `/faceless-explainer`, BRIEF.md, etc.) on top of it;
that path resolves voice through `media-use` (HeyGen/Kokoro), which bypasses
this project's XTTS/Piper decision (Phase 3) silently. Load `/hyperframes-core`,
`/hyperframes-animation`, `/hyperframes-creative`, `/hyperframes-cli` directly
as domain references — never the top-level `/hyperframes` router itself.

## Format routing — video vs. deck vs. web-slides vs. standalone diagram

When Nick's direction doesn't say which output format he wants, decide from
these signals before doing anything else — ask if genuinely tied, don't guess:

| Signal in the request | Format | Skill |
|---|---|---|
| Mentions narration, voiceover, "walk through," "explain out loud," or is meant to be watched/played | Narrated video | `video-presentation` |
| Mentions a meeting, "send over," "read at their own pace," speaker notes, or an outline/bullet list with no narration mentioned | Static deck | `slide-deck` |
| Mentions a browser page you click/scroll through, "web slides," "HTML deck," or "like ChessLoop" | Web-slide HTML deck (separate pipeline — lives in `presentation/`, not `idea/Presentation`, not built with HyperFrames) | `web-slide-presentation` |
| A single concept/architecture/flow with no surrounding narrative arc — nothing to sequence over time | Standalone diagram | `diagram-builder` |
| Source material already reads like spoken prose (sentences, not bullets) | Narrated video | script is already Stage 1 here |
| Source material already reads like an outline/spec/README (bullets, not prose) | Static deck | outline is already Stage 1 in `slide-deck` |
| Explicit "quick," "just the gist," "one-pager" with no watch/present cue | Static deck (cheapest to produce; video can follow if it lands) | `slide-deck` |
| No signal at all — a bare research/topic brief ("build something on X") | — | **Ask.** Video vs. deck is a real cost divergence (video = narration + Opus composition authoring; deck = one mechanical script run), not a default worth guessing |

Cross-cutting: a video and a deck on the same material can share the same
authored prose — narration segments (Stage 1 below) and `slide-deck`'s speaker
notes are the same script, written once. If Nick wants both, author the script
once and feed both pipelines.

They now also share a **layout vocabulary** (list · taxonomy · compare · steps
· definition · statement · quote · stat · timeline · code · screenshot) and a
palette catalogue, so the same beat maps to the same shape in all three
outputs. See "Scene shape vocabulary" in Stage 3b-2 below,
`web-slide-presentation`'s "Layout variety", and `slide-deck`'s "Layout
vocabulary" — one table, three renderers.

This skill is the *conductor*. It does not re-teach HyperFrames — the domain
skills own that (`/hyperframes-core`, `/hyperframes-animation`,
`/hyperframes-creative`, `/hyperframes-cli`). It owns two things they don't:

1. **The narration-first timing model** — real audio durations drive the
   visuals, not the reverse. This is what makes a *narrated video* instead of
   slides with a voiceover glued on.
2. **The wiring** to this project's local tools — `scripts/narrate.py` (XTTS
   :8300 / Piper :8001), `scripts/diagram.py` (via `diagram-builder`), and the
   HyperFrames project at `idea/Presentation/hyperframes/`.

**Model.** Composition authoring (Stage 3) is Opus work — layout, pacing,
animation, and timing are compounding judgment calls. Everything else (Stages
1, 2, 4, 5) is mechanical; if the session is only running the scripts and the
render loop, **say a switch down to Sonnet fits** and stop spending Opus on it.

## Pipeline at a glance

```
Stage 1  script → segments.json        (author: one beat per segment)
Stage 2  narrate.py → per-segment WAV + audio_meta.json (REAL durations)
Stage 3  compose index.html            ← the durations drive the timeline  [OPUS]
Stage 4  diagram.py → PNG/SVG          embed as static <img> clips
Stage 5  npm run check && npm run render → MP4   (HyperFrames muxes the audio)
```

The load-bearing idea: **Stage 2 happens before Stage 3.** You render the voice
first so you author the visuals against measured durations, not guesses. A word
count is not a duration.

## Stage 1 — Script → segments

Author the narration as an ordered JSON list, **one segment per beat** — a
sentence or tight sentence-cluster that is a single visual thought:

```json
[
  {"id": "hook",   "text": "Most outages don't start with a crash. They start with a retry."},
  {"id": "setup",  "text": "One slow service. A caller that retries three times. Then its caller retries that."},
  {"id": "reveal", "text": "That's a retry storm — and it's why a 200-millisecond blip becomes a 20-minute outage."}
]
```

Segment granularity **is** your editing grid. Each segment is the smallest unit
you can independently time a visual against, so split where the visual should
change and keep them together where it shouldn't. Segment ids become audio
element ids downstream — keep them short, kebab/lower, stable.

Narration-writing craft (spoken cadence, "one idea per breath", writing to be
heard not read) lives in `hyperframes-core` → `references/script-format.md` and
`hyperframes-creative`. Follow them for the prose; this file owns the *segmenting*.

## Stage 2 — Narrate (measure the voice)

```bash
cd idea/Presentation
python3 scripts/narrate.py segments.json \
  --reference JonRichardson.wav --out-dir hyperframes/assets/audio
```

Writes `hyperframes/assets/audio/<id>.wav` per segment plus `audio_meta.json`
(`segments[].{id, path, duration_s, engine}`, `total_duration_s`). XTTS (:8300)
is primary; it auto-falls back to Piper (:8001) per segment if XTTS is down.
For fast iteration you can force draft voice by stopping XTTS, but **re-render
the final pass on XTTS** — Piper timing differs, and durations are the contract.

**Voice, speed and loudness.** Set by Nick 2026-08-06 and **built into
`narrate.py` as defaults** — you get them by running it, not by remembering
them. Only `--reference` still has to be passed.

| | Default | Opt out with |
|---|---|---|
| Voice | `JonRichardson.wav` (pass explicitly) | `--reference <other>` |
| Speed | 1.25× | `--speed 1.0` |
| Loudness | -18 LUFS | `--no-normalize` |

- `JonRichardson.wav` is the **only** reference uploaded as of 2026-08-06 —
  `SteveGibson.wav` and `HonestTrailers2.wav` are gone, and the old advice to
  reach for SteveGibson would now fail outright. Always confirm against
  `curl http://localhost:8300/api/references` rather than a remembered list.
  The standing ask is a British female reference; Nick can upload any clip via
  `POST http://localhost:8300/api/upload`.
- Speed is applied *after* generation (ffmpeg `atempo`, pitch preserved)
  because XTTS exposes no rate parameter.
- Loudness normalisation targets `scripts/loudness.py`'s `TARGET_LUFS`, the
  same constant the web-slide video exporter audits against — so narration,
  any embedded footage, and every other deck all sit at one level. Bring
  supplied footage to it with
  `python3 scripts/loudness.py normalize <file>` (video stream copied, never
  re-encoded), and check a whole set with `loudness.py measure <files…>`.
- **Crucially, `audio_meta.json` durations are measured after retiming and
  normalisation**, so the timeline contract below stays exact. Never retime or
  re-level the WAVs yourself downstream — that desyncs every duration the
  composition is built on.

**Read `audio_meta.json` into context before Stage 3** — those numbers are the
timeline's skeleton.

## Stage 3 — Compose (the judgment stage) — OPUS

Author `hyperframes/index.html` (and `compositions/*.html` sub-comps). Invoke
the HyperFrames skills for the *how* — this section is the *what to decide*.

Before writing any composition HTML: **read `/hyperframes-core`** (the contract
— `data-*` timing, `class="clip"`, `window.__timelines`, root-child media rule)
and **`/hyperframes-animation`** (pick 2–4 atomic motion rules, or load a scene
blueprint). Don't hand-roll from generic web knowledge; the framework has
non-obvious rules (seek-safe determinism, media must be a direct root child).

### 3a. Narration-driven timeline (do this first, in numbers)

Lay the audio track down before designing a single frame. Each segment becomes a
root-level `<audio class="clip">` whose `data-start` is the **cumulative sum** of
prior segment durations (+ any deliberate pause), and whose `data-duration` is
its own measured length:

```html
<!-- direct children of the composition root; HyperFrames owns playback + mux -->
<audio id="hook-vo"   class="clip" src="assets/audio/hook.wav"
       data-start="0"     data-duration="3.2" data-track-index="10" data-volume="1"></audio>
<audio id="setup-vo"  class="clip" src="assets/audio/setup.wav"
       data-start="3.2"   data-duration="4.6" data-track-index="10" data-volume="1"></audio>
<audio id="reveal-vo" class="clip" src="assets/audio/reveal.wav"
       data-start="7.8"   data-duration="5.1" data-track-index="10" data-volume="1"></audio>
```

The root `data-duration` = `total_duration_s` (+ trailing hold). **Add small
breaths** (150–400ms) between segments at scene changes or after a punchline —
back-to-back audio sounds rushed. Bake the breath into the *next* segment's
`data-start`, and the composition stays exactly as long as the voice plus the
pauses you chose. This audio spine is the one thing every visual times against.

There is **no separate ffmpeg mux step** — `hyperframes render` composites these
`<audio>` elements into the MP4 directly. Do not build one.

### 3b. Scene decomposition

Group segments into **scenes** — a scene is one visual context (one
background/layout that holds while the idea develops). Several narration
segments usually share a scene; the scene changes when the *subject* changes,
not on every sentence. Fewer, longer scenes read calmer and are less work than
one-slide-per-sentence. Author each non-trivial scene as a sub-composition
(`data-composition-src="compositions/<scene>.html"`) so the root stays legible;
keep per-scene media (audio, diagram `<img>`) at the **host root** as siblings —
sub-comps can't own media or reach host elements (see core → composition-patterns).

### 3b-2. Scene shape vocabulary — match the frame to the shape of the idea

Back-ported 2026-07-30 from AIVU's deck renderer, which learned this the
expensive way: given only two usable layouts, every generated slide came out a
bulleted list and the decks read as one slide repeated. HyperFrames can draw
anything, which makes the failure *easier* to hit here, not harder — a
composition author under time pressure reuses the scene that already works.

Before composing, name the **shape** of each scene's idea, then build that
shape. Eleven cover essentially everything; they're the same set the
`web-slide-presentation` template and `slide-deck` now carry, so a video and a
deck on the same script stay recognisably one product.

| Shape | The idea is… | Frame + motion |
|---|---|---|
| **list** | loose points that belong together | Stagger items in on the narration's own beats — one item per clause, not all five at `data-start`. |
| **taxonomy** | 2–4 parallel things | Cards land together, then the one being named lifts/brightens. Never animate all four in sequence; that claims an order the content doesn't have. |
| **compare** | A vs B, before/after | Split frame. Bring in the "before" side, hold, then the "after" — the wipe *is* the argument. Colour-code with the palette's success/warn, don't label with words alone. |
| **steps** | an ordered procedure | Numbered nodes revealed strictly in order, each holding as its own narration segment plays. The connector drawing between nodes is the motion; the nodes themselves can be still. |
| **definition** | one term to retain | Term at term size, alone, then the gloss fades under it. Hold longer than feels necessary — this is the scene people screenshot. |
| **statement** | one principle | Full-frame type, < 30 words, near-zero motion. A statement scene that moves is arguing with itself. |
| **quote** | someone's own words | Type sets in, attribution after. Let the voice carry it; a quote is a pause in the video's rhythm and should feel like one. |
| **stat** | 1–3 figures | Count-up or scale-in on the number only, label static. One figure per beat. |
| **timeline** | events in order | Spine draws left-to-right (or top-down), markers land as the narration reaches each. The draw is the clock. |
| **code** | a listing + what it means | Listing left, anchors right. Highlight the line the narration is on — a code scene with no line highlighting is a screenshot. |
| **screenshot/diagram** | the real artifact | The `cards-image` / Stage 4 case: static asset in from the side, held for its whole segment. |
| **photo backdrop** | tone, not information | Editorial imagery behind the words — see "Photography" below. Slow push-in only; never a hard move. |

Three rules that carry over unchanged from the deck pipelines:

1. **No shape above 60% of the video's scenes.** Same threshold, same reason.
   Count them before rendering; four list-scenes in a row is the thing viewers
   describe as "it got boring around the middle."
2. **Alternate presentation even within one shape.** The deck templates
   alternate `content-list` between stacked and split-rail for exactly this;
   the video equivalent is varying which side the frame is weighted to, or
   which axis items enter on. Content-free, so it can't cost you anything.
3. **On-screen text caps.** ≤ 5 items, ≤ 12 words each, ≤ 3 stats, ≤ 18 code
   lines, statement < 30 words, quote < 45. Tighter than the deck's, if
   anything: the viewer can't scroll back. Over a cap is a rewrite signal, not
   a reason to shrink the type.
4. **Imagery density — at least 1 in 3 scenes carries a photo, screenshot or
   diagram, and never more than 3 consecutive scenes without one.** Same floor
   as both deck pipelines, and it binds hardest here: a video viewer cannot
   skim ahead past a dull stretch, they just stop watching. The opening and
   closing scenes get imagery by default. Plan it with the beat sheet in
   Stage 1 and resolve the whole set with `imagery.py batch` — imagery added
   "later" in a video pipeline means re-timing scenes you already built.

### 3c. Layout (per scene)

1920×1080. One focal idea per scene; if two ideas compete, it's two scenes.
Keep a safe margin (~64px) off every edge. Build visual hierarchy — the thing
the narration is naming right now is the largest / brightest / most-centered
element. Put the scene's full-bleed background on an absolute-inset **child**,
never the root (the renderer can drop a root background to black). Palette and
type: muted/subtle per Nick's standing UI preference; defer to
`hyperframes-creative` for the design spec.

**Palette shortcut.** If this video accompanies a deck (or should just look
like Lucent's other presentation output), take one of the seven
contrast-checked palettes in `web-slide-presentation/palettes.md` rather than
mixing colours per project — dark for anything watched on a screen, light only
if it will be projected. That file also carries the runnable contrast check any
hand-mixed palette has to pass; `npm run check`'s contrast pass is a floor, not
a substitute for choosing readable colours up front.

### 3d. Pacing & timing sync — the core skill

Motion is cut **to the narration**, using the segment boundaries from 3a as
anchors. The rules that matter:

- **Land the entrance when the words land.** An element animates in *as* the
  narration first refers to it — not a beat early (spoils it), not late (dead
  air). The anchor is that segment's `data-start`.
- **Hold for comprehension.** After it lands, a visual stays put long enough to
  be read *and* heard — at least its segment's duration. Never yank a diagram
  off screen while the voice is still explaining it.
- **Animate in the gaps, rest under dense narration.** Big motion competes with
  words. Put transitions and reveals in the breaths between segments; when the
  narration is information-dense, hold the frame still and let the voice carry.
- **One emphasis at a time.** If three things move at once the eye finds none.
  Sequence reveals to the order the script names them.
- **Match energy to register.** A hook can snap; an explanation should settle.
  Ease and duration are tone — see `hyperframes-animation` for the eases.

Timelines are paused and registered on `window.__timelines`; all host-media
motion is authored on the **main** timeline at **global** time (segment
`data-start` + local offset), because sub-comp timelines can't drive host
elements. Author, then verify with per-frame snapshots — not just `check`.

## Stage 3b-3. Photography — Openverse imagery

Added 2026-07-30, shared with the two deck pipelines. Same tool, same rules:

```bash
cd idea/Presentation
python3 scripts/imagery.py resolve "server room datacenter" \
  --topic "Where firewall rules actually run" \
  --out-dir hyperframes/assets/images --name hero --tint '#00bfff'
python3 scripts/imagery.py credits hyperframes/assets/images --short
```

Place the frozen file as a root-level `<img class="clip">` behind the scene's
content, exactly like a diagram, with an absolute-inset **child** carrying it
(never the root background — the renderer can drop that to black).

Five rules, three of them video-specific:

1. **Editorial, never explanatory.** Search the *noun in the scene you want*,
   not the idea the narration teaches — retrieval works for concrete nouns and
   fails for abstract concepts. Anything that must explain is a diagram.
2. **Bake the tint** (`--tint`). There is no CSS-filter layer you can rely on
   through a render, and the duotone treatment is what makes unrelated stock
   photography read as one film rather than a slideshow of other people's
   pictures.
3. **Scrim every photo you put words on.** A gradient overlay child, not a
   reduced text opacity — darkening the image is always the right fix for
   contrast, dimming the type never is. `npm run check`'s contrast pass will
   catch the worst cases; don't rely on it to have taste.
4. **Motion: a slow push-in (1.02→1.06 scale over the whole segment) and
   nothing else.** This is the one place a Ken Burns move earns its keep —
   it keeps a still frame alive under a long narration segment. Pans, wipes
   and parallax on editorial stills read as a screensaver.
5. **Credit is required.** CC-BY is a licence. Put the short credit in a
   corner caption for the segment's duration, or run a credits card before the
   end plate — `imagery.py credits --short` prints the strings. A video that
   ships without them is not distributable.

## Stage 4 — Embed diagrams

When a scene needs a technical diagram, hand off to the **`diagram-builder`**
skill (pick tool → author source → `scripts/diagram.py` exports PNG/SVG). Drop
the exported file into `hyperframes/assets/diagrams/` and place it as a
root-level static `<img class="clip">` timed like any other clip:

```html
<img id="arch-diagram" class="clip" src="assets/diagrams/retry-storm.png"
     data-start="7.8" data-duration="5.1" data-track-index="1"
     style="position:absolute; left:64px; top:120px; width:1000px" />
```

Time it to the segment whose narration explains it (3d: land on entrance, hold
through the segment). Prefer SVG from Draw.io when you want crisp scaling;
Excalidraw/Sketchlab are PNG-only. Diagrams are static assets — animate them
with entrance/emphasis on the main timeline, don't expect them to self-animate.

## Stage 5 — Check & render (mechanical — Sonnet)

```bash
cd idea/Presentation/hyperframes
npm run check          # lint + runtime + layout + motion + contrast — fix ALL errors
npm run dev            # preview server: run_in_background:true, never foreground
npm run render         # → MP4, audio muxed in
```

`npm run dev` is a long-running server — always background it (see hyperframes
CLAUDE.md). Run `check` after every edit and clear all errors before rendering;
review warnings. For CLI depth (render flags, quality/fps, preview, publish,
snapshot/compare, doctor) use `/hyperframes-cli`. Verify the final MP4 with
`ffprobe` (duration should match `total_duration_s` + holds; confirm an audio
stream is present).

## Where things live

| Thing | Path |
|---|---|
| Composition project | `idea/Presentation/hyperframes/` (`index.html`, `compositions/`, `assets/`) |
| Narration script + audio | `hyperframes/assets/audio/` (`<id>.wav`, `audio_meta.json`) |
| Diagrams | `hyperframes/assets/diagrams/` |
| Narration engine | `scripts/narrate.py` → XTTS :8300 (primary) / Piper :8001 (fallback) |
| Diagram export | `scripts/diagram.py` via `diagram-builder` skill → Draw.io :8103 / Sketchlab :8114 |
| Rendered output | `hyperframes/renders/` |

If a local service is down, check `idea/PORTS.md` / `idea/project-health.sh`.
Deeper HyperFrames intent-routing (URL/PR/footage/music inputs, `/slideshow`,
`/faceless-explainer`, etc.) lives in `/hyperframes` — this skill is the path
for *script/outline → narrated video* specifically.
