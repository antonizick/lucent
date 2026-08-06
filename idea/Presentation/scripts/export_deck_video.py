#!/usr/bin/env python3
"""Render a hand-authored web-slide deck (the ChessLoop/`web-slide-presentation`
family, under `presentation/<slug>/`) into a single narrated MP4.

Each slide is screenshotted with Playwright and held for exactly as long as its
narration runs; a slide carrying a `<video>` gets its still held for the
narration and then **the real clip spliced into the timeline** — the whole
reason this exists. A screenshot-only exporter turns an embedded video into a
frozen poster frame, which is the one thing a video slide must not become.

Distinct from `idea/PATH/backend/app/video_export.py`, which does the same job
for PATH's *generated* lesson decks and is driven by that app's own job
registry. The animation-settle trick below is ported from it deliberately —
a fixed delay is wrong on any slide whose entrance animation outruns the guess.

    python3 export_deck_video.py presentation/PATH -o /tmp/path-deck.mp4
    python3 export_deck_video.py presentation/PATH --dry-run   # timeline only

Requires: playwright (+ `playwright install chromium`), ffmpeg, ffprobe.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loudness  # noqa: E402  — shares the ONE loudness target with narrate.py

# Interactive chrome has no meaning in a rendered video: nobody can tick "Auto
# Advance Slides" in an MP4, and a checkbox burned into the lower-right corner
# of every frame just reads as a mistake. Hidden at capture time rather than
# removed from the deck, because the live deck genuinely needs these.
HIDE_FOR_CAPTURE = ".nav-controls { display: none !important; }"

# Every segment is encoded to these before concatenation. The concat demuxer
# copies streams without re-encoding, which it can only do if the parts already
# agree on codec, resolution, frame rate, pixel format and sample rate.
V_CODEC = ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"]
A_CODEC = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
SILENT_IN = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]

# Ceiling on the settle wait, not the normal case — the real wait is however
# long the slide's own animations take. Only bounds a slide that never reports
# finished (an infinite animation would otherwise stall the whole render).
MAX_SETTLE_MS = 4000

SETTLE_JS = """
async (maxWaitMs) => {
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const settle = Promise.all(document.getAnimations().map((a) => a.finished.catch(() => {})));
  const timeout = new Promise((r) => setTimeout(r, maxWaitMs));
  await Promise.race([settle, timeout]);
}
"""


@dataclass
class Segment:
    """One stretch of the finished video."""
    kind: str                      # "still" | "clip"
    slide: int                     # 0-based slide index it came from
    duration: float
    still: Optional[Path] = None   # kind == "still"
    audio: Optional[Path] = None   # kind == "still", None means silence
    clip: Optional[Path] = None    # kind == "clip"

    def label(self) -> str:
        if self.kind == "clip":
            return f"slide {self.slide:02d}  CLIP   {self.clip.name}"
        source = self.audio.name if self.audio else "(silent)"
        return f"slide {self.slide:02d}  still  {source}"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{proc.stderr[-2000:]}")
    return proc


def probe_duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)]).stdout
    return float(out.strip())


def has_audio_stream(path: Path) -> bool:
    out = run(["ffprobe", "-v", "error", "-select_streams", "a",
               "-show_entries", "stream=index", "-of", "csv=p=0", str(path)]).stdout
    return bool(out.strip())


def collect(deck: Path, frames_dir: Path, width: int, height: int,
            silent_hold: float) -> list[Segment]:
    """Drive the deck in a browser: screenshot every slide, and pick up the
    narration and any embedded clip that belongs to it."""
    from playwright.sync_api import sync_playwright

    index = deck / "index.html"
    if not index.is_file():
        raise SystemExit(f"no index.html in {deck}")

    segments: list[Segment] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(index.resolve().as_uri())
            page.add_style_tag(content=HIDE_FOR_CAPTURE)

            # Ask the DECK for its own audio mapping rather than re-implementing
            # the data-audio / data-silent / positional rule here. Two copies of
            # that rule would drift, and the drift is silent: the export would
            # simply hold the wrong slide for the wrong narration.
            if not page.evaluate("typeof audioFor === 'function'"):
                raise SystemExit(
                    f"{index} has no audioFor() — this exporter only understands decks "
                    "built from the web-slide-presentation template.html."
                )

            sections = page.locator("section.slide")
            for i in range(sections.count()):
                section = sections.nth(i)
                section.scroll_into_view_if_needed()
                page.evaluate(SETTLE_JS, MAX_SETTLE_MS)

                src = page.evaluate("(i) => audioFor(i)", i)
                audio = None
                if src:
                    candidate = deck / src
                    if not candidate.is_file():
                        raise SystemExit(
                            f"slide {i:02d} wants {src}, which does not exist. "
                            "Generate the narration before exporting."
                        )
                    audio = candidate

                still = frames_dir / f"slide_{i:03d}.png"
                section.screenshot(path=str(still))
                segments.append(Segment(
                    kind="still", slide=i, still=still, audio=audio,
                    duration=probe_duration(audio) if audio else silent_hold,
                ))

                # A clip on this slide plays AFTER its narration has introduced it,
                # mirroring how a viewer actually experiences the live deck.
                video = section.locator("video")
                if video.count():
                    if video.count() > 1:
                        raise SystemExit(f"slide {i:02d} has {video.count()} videos; expected at most 1")
                    if not video.get_attribute("poster"):
                        print(f"  ! slide {i:02d}: <video> has no poster — its still will be a "
                              f"black rectangle. See template.html TYPE: video-half.", file=sys.stderr)
                    vsrc = video.get_attribute("src")
                    if not vsrc:
                        raise SystemExit(f"slide {i:02d}: <video> has no src attribute")
                    clip = deck / vsrc
                    if not clip.is_file():
                        raise SystemExit(f"slide {i:02d} wants {vsrc}, which does not exist")
                    segments.append(Segment(kind="clip", slide=i, clip=clip,
                                            duration=probe_duration(clip)))
            page.close()
        finally:
            browser.close()
    return segments


def audit_loudness(segments: list[Segment]) -> bool:
    """Report every source's level against the house target. Returns True if OK.

    Deliberately reports rather than repairs. The file on disk is what the *web*
    deck plays too, so fixing it here would leave the browser version quiet and
    only the export correct — one source of truth, normalised at build time with
    `loudness.py normalize`. This is the check that stops that step being
    forgotten silently.
    """
    sources: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for s in segments:
        p = s.clip if s.kind == "clip" else s.audio
        if p and p not in seen:
            seen.add(p)
            sources.append(("CLIP" if s.kind == "clip" else "narr", p))
    if not sources:
        return True

    print("\nLoudness (target %.1f LUFS, tolerance %.1f LU):" % (
        loudness.TARGET_LUFS, loudness.TOLERANCE_LU), file=sys.stderr)
    worst_delta, worst_name, clips, narrs = 0.0, "", [], []
    for kind, path in sources:
        try:
            m = loudness.measure(path)
        except loudness.LoudnessError as e:
            print(f"  {kind}  {path.name:<34} unmeasurable: {e}", file=sys.stderr)
            continue
        delta = loudness.off_target(m)
        (clips if kind == "CLIP" else narrs).append(m["input_i"])
        if abs(delta) > abs(worst_delta):
            worst_delta, worst_name = delta, path.name
        flag = "  <-- off target" if abs(delta) > loudness.TOLERANCE_LU else ""
        print(f"  {kind}  {path.name:<34} I={m['input_i']:7.2f} LUFS "
              f"({delta:+.2f} LU){flag}", file=sys.stderr)

    ok = abs(worst_delta) <= loudness.TOLERANCE_LU
    # The number that actually matters is the STEP the viewer hears when the
    # deck cuts from a narrated slide into a clip — not either one's absolute
    # level. Report it explicitly.
    if clips and narrs:
        step = abs(sum(clips) / len(clips) - sum(narrs) / len(narrs))
        print(f"  narration vs clip step: {step:.2f} LU "
              f"({'inaudible' if step <= 1 else 'audible' if step <= 2 else 'OBVIOUS'})",
              file=sys.stderr)
        ok = ok and step <= loudness.TOLERANCE_LU
    if not ok:
        print(f"  WARNING: {worst_name} is {abs(worst_delta):.2f} LU off target. Fix before "
              f"shipping:\n    python3 loudness.py normalize <file>", file=sys.stderr)
    return ok


def encode(seg: Segment, out: Path, width: int, height: int, fps: int, crf: int) -> None:
    fit = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
           f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1")

    if seg.kind == "still":
        cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-i", str(seg.still)]
        cmd += ["-i", str(seg.audio)] if seg.audio else SILENT_IN
        cmd += ["-map", "0:v:0", "-map", "1:a:0",
                "-t", f"{seg.duration:.3f}", "-vf", fit, "-r", str(fps),
                *V_CODEC, "-tune", "stillimage", "-crf", str(crf), *A_CODEC, str(out)]
    else:
        cmd = ["ffmpeg", "-y", "-i", str(seg.clip)]
        # A clip with no audio track still needs one, or concat gets a part
        # whose stream layout differs from every other part and refuses to copy.
        silent = not has_audio_stream(seg.clip)
        if silent:
            cmd += SILENT_IN
        cmd += ["-map", "0:v:0", "-map", "1:a:0" if silent else "0:a:0",
                "-vf", f"{fit},fps={fps}", "-r", str(fps),
                *V_CODEC, "-crf", str(crf), *A_CODEC]
        if silent:
            cmd += ["-shortest"]
        cmd += [str(out)]
    run(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deck", type=Path, help="deck directory containing index.html")
    ap.add_argument("-o", "--out", type=Path, help="output mp4 (default: <deck>/<slug>.mp4)")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crf", type=int, default=20, help="x264 quality, lower is better (default 20)")
    ap.add_argument("--silent-hold", type=float, default=4.0,
                    help="seconds to hold a slide with no narration (default 4)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the timeline and exit without encoding")
    args = ap.parse_args()

    deck = args.deck.resolve()
    out = (args.out or deck / f"{deck.name}.mp4").resolve()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found on PATH")

    with tempfile.TemporaryDirectory(prefix="deckvid-") as td:
        work = Path(td)
        frames = work / "frames"
        frames.mkdir()

        print(f"Capturing {deck.name} at {args.width}x{args.height} …", file=sys.stderr)
        segments = collect(deck, frames, args.width, args.height, args.silent_hold)

        total = sum(s.duration for s in segments)
        clips = sum(1 for s in segments if s.kind == "clip")
        print(f"\n{len(segments)} segments, {clips} embedded clip(s), "
              f"{total / 60:.1f} min total:", file=sys.stderr)
        for s in segments:
            print(f"  {s.duration:7.2f}s  {s.label()}", file=sys.stderr)

        audit_loudness(segments)

        if args.dry_run:
            return 0

        parts: list[Path] = []
        for n, seg in enumerate(segments):
            part = work / f"part_{n:03d}.mp4"
            print(f"\rEncoding {n + 1}/{len(segments)} …", end="", file=sys.stderr, flush=True)
            encode(seg, part, args.width, args.height, args.fps, args.crf)
            parts.append(part)
        print(file=sys.stderr)

        listing = work / "parts.txt"
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", str(out)])

    got = probe_duration(out)
    # The concat is lossless, so the finished file must match the timeline that
    # was printed above. A mismatch means a part was dropped or truncated —
    # exactly the silent failure this exporter exists to avoid.
    if abs(got - total) > 1.0 + 0.05 * len(segments):
        print(f"WARNING: expected ~{total:.1f}s, got {got:.1f}s — a segment may have "
              f"been dropped.", file=sys.stderr)
    print(f"\n{out}  ({out.stat().st_size / 1e6:.1f} MB, {got / 60:.1f} min)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
