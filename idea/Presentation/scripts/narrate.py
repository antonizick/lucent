#!/usr/bin/env python3
"""Narration helper: script segments -> XTTS (primary) or Piper (fallback) WAV files + duration metadata.

Usage:
    narrate.py segments.json --reference JonRichardson.wav [--out-dir assets/audio] [--speed 1.25]

segments.json: [{"id": "intro", "text": "..."}, ...]
Writes {out-dir}/{id}.wav per segment plus {out-dir}/audio_meta.json:
    {"segments": [{"id", "path", "duration_s", "engine"}], "total_duration_s"}
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loudness  # noqa: E402  — shares the ONE loudness target with the video exporter

XTTS_BASE = "http://localhost:8300"
PIPER_URL = "http://localhost:8001/speak"


def resolve_reference(name):
    with urllib.request.urlopen(f"{XTTS_BASE}/api/references") as r:
        refs = json.load(r)
    for ref in refs:
        if name in (ref["filename"], ref["original"]):
            return ref["filename"]
    raise SystemExit(f"Unknown XTTS reference {name!r}. Available: {[r['original'] for r in refs]}")


def xtts_generate(text, reference, language):
    data = urllib.parse.urlencode({"text": text, "reference": reference, "language": language}).encode()
    req = urllib.request.Request(f"{XTTS_BASE}/api/generate", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        filename = json.load(r)["filename"]
    with urllib.request.urlopen(f"{XTTS_BASE}/audio/outputs/{filename}", timeout=30) as r:
        return r.read()


def piper_generate(text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        PIPER_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    return base64.b64decode(payload["audio"])


def wav_duration(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def retime(path, speed):
    """Speed a rendered WAV up or down in place, preserving pitch.

    Post-processing rather than an engine setting because XTTS has no speed
    parameter at all (`/api/generate` takes text/reference/language, nothing
    else) — and doing it here means the knob works identically for Piper,
    whose own speed control is global voice-box state we'd have to set and
    restore. ffmpeg's atempo is a phase-vocoder: 1.25 is 25% faster at the
    same pitch, not a chipmunk.

    atempo is only defined over 0.5-2.0 per instance, so anything outside
    that range is chained.
    """
    factors, remaining = [], speed
    while remaining > 2.0:
        factors.append(2.0); remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5); remaining /= 0.5
    factors.append(remaining)
    chain = ",".join(f"atempo={f:.6g}" for f in factors)

    tmp = path + ".retime.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-filter:a", chain, tmp],
                   check=True, capture_output=True)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", help="JSON file: list of {id, text}")
    ap.add_argument("--reference", help="XTTS voice reference: original filename or stored hash (required unless --engine piper)")
    ap.add_argument("--language", default="en")
    ap.add_argument("--out-dir", default="assets/audio")
    ap.add_argument("--engine", choices=["auto", "xtts", "piper"], default="auto",
                    help="auto (default): XTTS with Piper fallback. piper: force Piper for every segment "
                         "(uses whatever voice/speed is currently active on the voice box).")
    ap.add_argument("--speed", type=float, default=1.25,
                    help="Playback rate applied after generation, pitch preserved (ffmpeg atempo). "
                         "DEFAULT 1.25 — the house pace for decks and videos alike; the "
                         "as-generated rate reads as too slow. Pass --speed 1.0 to opt out.")
    ap.add_argument("--no-normalize", action="store_true",
                    help=f"Skip loudness normalisation. Off by default: every segment is brought "
                         f"to {loudness.TARGET_LUFS} LUFS so narration matches embedded video "
                         f"and any other narration, whatever engine or voice produced it.")
    args = ap.parse_args()
    if args.speed <= 0:
        ap.error("--speed must be positive")
    if args.engine != "piper" and not args.reference:
        ap.error("--reference is required unless --engine piper")

    segments = json.loads(open(args.script).read())
    reference = resolve_reference(args.reference) if args.engine != "piper" else None
    os.makedirs(args.out_dir, exist_ok=True)

    meta = {"segments": [], "total_duration_s": 0.0}
    levels = []
    for seg in segments:
        out_path = os.path.join(args.out_dir, f"{seg['id']}.wav")
        if args.engine == "piper":
            audio = piper_generate(seg["text"])
            engine = "piper"
        else:
            engine = "xtts"
            try:
                audio = xtts_generate(seg["text"], reference, args.language)
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"[{seg['id']}] XTTS unavailable ({e}), falling back to Piper", file=sys.stderr)
                audio = piper_generate(seg["text"])
                engine = "piper"
        with open(out_path, "wb") as f:
            f.write(audio)
        if args.speed != 1.0:
            retime(out_path, args.speed)
        if not args.no_normalize:
            # Every segment to the same level, so the deck doesn't step in
            # volume between slides, between voices, or against an embedded
            # video clip normalised to the same constant.
            r = loudness.normalize(Path(out_path))
            if r["skipped"]:
                print(f"[{seg['id']}] loudness: {r['skipped']}", file=sys.stderr)
            else:
                levels.append((seg["id"], r["after"]["input_i"]))
        # Measured AFTER retiming and normalisation, so audio_meta durations
        # always describe the file on disk — the deck and the video exporter
        # both time slides off it.
        duration = wav_duration(out_path)
        meta["segments"].append(
            {"id": seg["id"], "path": out_path, "duration_s": round(duration, 3), "engine": engine}
        )
        meta["total_duration_s"] += duration

    meta["total_duration_s"] = round(meta["total_duration_s"], 3)
    meta["speed"] = args.speed
    meta["loudness_lufs"] = None if args.no_normalize else loudness.TARGET_LUFS
    meta_path = os.path.join(args.out_dir, "audio_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Wrote {len(segments)} segment(s) at speed {args.speed}x -> {meta_path}")

    # Report the spread rather than trusting the filter — a segment that missed
    # the target is a segment the viewer hears jump, and it must not pass
    # silently just because ffmpeg exited 0.
    if levels:
        worst_id, worst_i = max(levels, key=lambda kv: abs(kv[1] - loudness.TARGET_LUFS))
        drift = abs(worst_i - loudness.TARGET_LUFS)
        print(f"Loudness: {len(levels)} segment(s) at {loudness.TARGET_LUFS} LUFS; "
              f"worst is {worst_id} at {worst_i:.2f} ({drift:.2f} LU off)")
        if drift > loudness.TOLERANCE_LU:
            print(f"WARNING: {worst_id} is {drift:.2f} LU off target "
                  f"(tolerance {loudness.TOLERANCE_LU}) — listen before shipping.",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
