# Version-controlled skills

The skills in this directory are the **real files**. Claude Code loads skills
from `~/.claude/skills/`, which is outside any repo, so the entries there are
symlinks pointing back here:

```
~/.claude/skills/web-slide-presentation -> <repo>/.claude/skills/web-slide-presentation
~/.claude/skills/video-presentation     -> <repo>/.claude/skills/video-presentation
```

One set of bytes, two paths. Editing through either path edits the same file, so
the repo copy and the loaded skill cannot drift apart — which they did when this
was a plain copy.

Set up 2026-08-06. Only these two skills are tracked; everything else in
`~/.claude/skills/` (`hyperframes*`, `diagram-builder`, `excalidraw-diagram`,
`sketch-lab`, …) is still an unversioned local directory.

## Recreating the links on a new machine

After cloning, the skills exist in the repo but Claude Code cannot see them
until the links are made. From the repo root:

```bash
for s in web-slide-presentation video-presentation; do
  [ -e "$HOME/.claude/skills/$s" ] && [ ! -L "$HOME/.claude/skills/$s" ] && {
    echo "REAL directory already at ~/.claude/skills/$s — move it aside first"; continue; }
  ln -sfn "$PWD/.claude/skills/$s" "$HOME/.claude/skills/$s"
done
ls -l ~/.claude/skills/ | grep -E 'web-slide|video-presentation'
```

The guard matters: if a real directory is already there, blindly replacing it
throws away whatever local edits it holds. Reconcile first, then link.

## Gotchas

- **The links are absolute.** Moving or renaming the repo breaks them. Re-point
  the links — do not recreate the files, or you are back to two copies drifting.
- **Editing a `SKILL.md` now dirties this repo's working tree.** That is the
  intent: skill changes are commits.
- **A skill is not just its `SKILL.md`.** Both of these drive scripts that live
  outside this directory — `narrate.py`, `loudness.py` and
  `export_deck_video.py` in `idea/Presentation/scripts/`. `idea/` is gitignored,
  so those three are force-added; **any new script there needs `git add -f`** or
  it will be silently untracked.
- `web-slide-presentation/template.html` is the source of truth for deck markup
  and is copied per deck into `presentation/<slug>/index.html`. Change the
  template, not a built deck, when fixing something that affects every deck.

## What each skill owns

| Skill | Deliverable |
|---|---|
| `web-slide-presentation` | Scroll-snap HTML decks with per-slide narration (the ChessLoop pattern), plus MP4 export |
| `video-presentation` | Narrated animated MP4s built with HyperFrames |

Both share the narration pipeline, and both take their voice, speed and loudness
defaults from the tooling rather than from prose — see `loudness.py`, which owns
the single loudness target that narration and embedded video are both held to.
