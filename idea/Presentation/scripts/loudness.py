#!/usr/bin/env python3
"""One loudness target for everything a presentation plays.

The problem this exists to prevent: a deck's TTS narration and a supplied video
clip are produced by completely unrelated processes, so they arrive at
completely unrelated levels. Measured 2026-08-06 on the first deck to embed a
video: narration at -18.0 LUFS, the clip at -29.96 LUFS. Twelve decibels. The
viewer hears it instantly and reaches for the volume knob.

Matching them is not a step someone should have to remember, so it isn't one —
`narrate.py` normalises every segment it renders through here, and
`export_deck_video.py` measures embedded clips against the same constants and
complains when they don't match. Both import TARGET_* from this module, so
"as identical as technically feasible" is a property of the code rather than
of anyone's diligence.

Why loudness (EBU R128) and not peak or gain:
  * Perceived loudness is what the viewer notices; peak level is not a proxy
    for it. That clip peaked at only -3.25 dBTP while sounding 12 dB quiet.
  * Flat gain therefore cannot fix it — +12 dB on a -3.25 dBTP source clips by
    nearly 9 dB. `loudnorm` includes a limiter, so it can raise perceived level
    without destroying the peaks.

    python3 loudness.py measure presentation/PATH/audio/*.mp3 presentation/PATH/video/*.mp4
    python3 loudness.py normalize presentation/PATH/video/clip.mp4      # in place
    python3 loudness.py normalize in.wav -o out.wav
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# The house level. -18 LUFS is where narrate.py's XTTS output already landed, so
# adopting it means narration needed no change and every other source comes to
# meet it. TP -1.5 dBTP leaves headroom for the lossy encode that follows.
TARGET_LUFS = -18.0
TARGET_TP = -1.5
TARGET_LRA = 11.0

# How far apart two sources may sit before a viewer notices a step in level.
# 1 LU is around the threshold of perceptibility on speech; 2 is comfortably
# audible, so that is where the tooling starts complaining.
TOLERANCE_LU = 2.0

# EBU R128 integrated loudness is only meaningful over a few seconds of audio.
# Below this, measurement is noise and normalising on it would make a short
# segment louder or quieter than its neighbours for no good reason.
MIN_MEASURABLE_S = 3.0


class LoudnessError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise LoudnessError(f"{cmd[0]} failed:\n{proc.stderr[-1500:]}")
    return proc.stderr + proc.stdout


def duration(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out.strip())


def _stream(path: Path, kind: str, field: str) -> Optional[str]:
    out = _run(["ffprobe", "-v", "error", "-select_streams", kind,
                "-show_entries", f"stream={field}", "-of", "csv=p=0", str(path)])
    return out.strip().splitlines()[0] if out.strip() else None


def has_video(path: Path) -> bool:
    return _stream(path, "v", "index") is not None


def measure(path: Path) -> dict:
    """Integrated loudness / true peak / range, via a full loudnorm analysis pass."""
    out = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                "-af", f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"
                       ":print_format=json", "-f", "null", "-"])
    match = re.search(r"\{[^{}]*input_i[^{}]*\}", out, re.S)
    if not match:
        raise LoudnessError(f"no loudness measurement for {path} — is there an audio track?")
    d = json.loads(match.group(0))
    return {k: float(v) for k, v in d.items() if k != "normalization_type"} | {
        "normalization_type": d.get("normalization_type")
    }


def off_target(m: dict) -> float:
    """Signed distance from the house level, in LU."""
    return m["input_i"] - TARGET_LUFS


def normalize(src: Path, dst: Optional[Path] = None) -> dict:
    """Bring `src` to the house level. Returns {"before", "after", "skipped"}.

    Two-pass: measure, then apply with those measurements, which is materially
    more accurate than single-pass and lets ffmpeg use a static gain whenever
    the target is reachable without clipping.

    **The video stream is always copied, never re-encoded** — an embedded clip
    is normalised for its audio alone, and the picture must come through
    bit-identical. `verify_video_untouched` proves it did.
    """
    dst_final = dst or src
    if duration(src) < MIN_MEASURABLE_S:
        return {"before": None, "after": None,
                "skipped": f"under {MIN_MEASURABLE_S}s — too short to measure reliably"}

    before = measure(src)
    filt = (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"
            f":measured_I={before['input_i']}:measured_TP={before['input_tp']}"
            f":measured_LRA={before['input_lra']}:measured_thresh={before['input_thresh']}"
            f":offset={before['target_offset']}")

    # loudnorm resamples to 192 kHz internally; without an explicit -ar the
    # output file silently inherits that, which bloats WAVs and surprises
    # anything reading the sample rate back.
    rate = _stream(src, "a", "sample_rate") or "48000"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if has_video(src):
        cmd += ["-c:v", "copy"]
    cmd += ["-af", filt, "-ar", rate]
    if src.suffix.lower() == ".wav":
        cmd += ["-c:a", "pcm_s16le"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / f"norm{src.suffix}"
        _run(cmd + [str(tmp)])
        after = measure(tmp)
        dst_final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(dst_final))
    return {"before": before, "after": after, "skipped": None}


def video_md5(path: Path) -> str:
    """MD5 of the raw video packets — unchanged by an audio-only rewrite."""
    out = _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v", "-c", "copy",
                "-f", "md5", "-"])
    return out.strip().split("=")[-1]


def _cmd_measure(args) -> int:
    worst = 0.0
    for f in args.files:
        p = Path(f)
        try:
            m = measure(p)
        except LoudnessError as e:
            print(f"  {p.name:<38} ERROR: {e}"); continue
        delta = off_target(m)
        worst = max(worst, abs(delta))
        flag = "  <-- off target" if abs(delta) > TOLERANCE_LU else ""
        print(f"  {p.name:<38} I={m['input_i']:7.2f} LUFS  TP={m['input_tp']:6.2f} dBTP"
              f"  ({delta:+.2f} LU){flag}")
    print(f"\nTarget {TARGET_LUFS} LUFS, tolerance {TOLERANCE_LU} LU. "
          f"Worst deviation: {worst:.2f} LU — {'PASS' if worst <= TOLERANCE_LU else 'FAIL'}")
    return 0 if worst <= TOLERANCE_LU else 1


def _cmd_normalize(args) -> int:
    src = Path(args.file)
    dst = Path(args.out) if args.out else src
    before_md5 = video_md5(src) if has_video(src) else None
    r = normalize(src, dst)
    if r["skipped"]:
        print(f"  {src.name}: skipped — {r['skipped']}")
        return 0
    print(f"  {src.name}: {r['before']['input_i']:.2f} -> {r['after']['input_i']:.2f} LUFS "
          f"(TP {r['after']['input_tp']:.2f} dBTP, {r['before']['normalization_type']})")
    if before_md5 is not None:
        same = before_md5 == video_md5(dst)
        print(f"  video stream {'IDENTICAL — picture untouched' if same else 'CHANGED — BUG'} "
              f"({before_md5})")
        if not same:
            return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure", help="report loudness of files against the house target")
    m.add_argument("files", nargs="+")
    m.set_defaults(fn=_cmd_measure)
    n = sub.add_parser("normalize", help="bring a file to the house target (video stream copied)")
    n.add_argument("file")
    n.add_argument("-o", "--out", help="write here instead of in place")
    n.set_defaults(fn=_cmd_normalize)
    args = ap.parse_args()
    try:
        return args.fn(args)
    except LoudnessError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
