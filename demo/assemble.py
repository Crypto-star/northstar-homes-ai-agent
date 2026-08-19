"""Assemble the demo video: screen recording + voiceover + burned-in captions.

    python demo/assemble.py

Inputs
    demo/raw/*.webm        Playwright screen recording (1920x1080, silent)
    demo/raw/beats.json    wall-clock offset of each narration beat
    demo/vo/*.mp3          one voiceover clip per beat
    demo/vo/timings.json   word-level timings from ElevenLabs

Output
    demo/edit/final.mp4

Method
    For each beat, take the matching slice of the recording. If the narration is
    longer than the slice, hold the slice's last frame until they match, so
    picture and voice never drift. Segments are encoded once with identical
    parameters and concatenated with `-c copy`, so nothing is re-encoded twice.
    Subtitles are burned LAST, after everything else is composited.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "demo" / "raw"
VO = ROOT / "demo" / "vo"
EDIT = ROOT / "demo" / "edit"
SEG = EDIT / "segments"

W, H, FPS = 1920, 1080, 30
CRF = "18"          # visually lossless for screen content
TAIL_PAD = 0.6      # seconds of held frame after each beat's narration ends

# YouTube-style captions: short chunks, sentence case, white on a heavy dark
# outline, sat above the bottom edge so the composer bar stays readable.
#
# Written as ASS rather than SRT + force_style. force_style values are packed
# into one filter-graph argument, so every comma and colon inside them has to be
# escaped, and ffmpeg 8 rejects several spellings that used to work. An ASS file
# carries its own style block and needs no escaping at all.
WORDS_PER_CAPTION = 6

CAPS = EDIT / "captions"

# Caption band geometry, in 1920x1080 space.
CAP_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
CAP_SIZE = 46
CAP_MAX_W = 1440           # wrap width; keeps lines short and readable
CAP_BOTTOM = 58            # distance from the bottom edge to the band's base
CAP_PAD_X, CAP_PAD_Y = 26, 14
CAP_RADIUS = 6
CAP_BG = (18, 18, 20, 214)  # near-black plate, the YouTube treatment
CAP_FG = (255, 255, 255, 255)


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(cmd[:8])}...\n{proc.stderr[-1500:]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_caption(text: str, path: Path) -> tuple[int, int]:
    """Draw one caption card as a transparent PNG. Returns its size.

    This ffmpeg build has no libass and no freetype, so the subtitles, ass and
    drawtext filters do not exist. Rendering the cards ourselves and compositing
    them with the plain overlay filter needs nothing extra from ffmpeg.
    """
    font = ImageFont.truetype(CAP_FONT, CAP_SIZE)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = _wrap(probe, text, font, CAP_MAX_W)

    widths = [probe.textlength(ln, font=font) for ln in lines]
    line_h = CAP_SIZE + 12
    w = int(max(widths)) + CAP_PAD_X * 2
    h = line_h * len(lines) + CAP_PAD_Y * 2

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=CAP_RADIUS, fill=CAP_BG)
    for i, ln in enumerate(lines):
        x = (w - widths[i]) / 2
        d.text((x, CAP_PAD_Y + i * line_h), ln, font=font, fill=CAP_FG)
    img.save(path)
    return w, h


MIN_CAPTION_WORDS = 3
MAX_CAPTION_GAP = 1.2


def chunk_words(words: list[dict], size: int) -> list[tuple[float, float, str]]:
    """Group words into caption cards, breaking early on sentence-final punctuation.

    Two rules beyond the obvious. A trailing one- or two-word card reads as a
    flicker, so a short group merges back into the one before it. And a card
    holds until the next one starts, as long as the pause is short — otherwise
    the caption blinks out during every breath the narrator takes.
    """
    groups: list[list[dict]] = []
    buf: list[dict] = []
    for w in words:
        buf.append(w)
        ends_sentence = w["word"].rstrip('"\')').endswith((".", "?", "!", ":"))
        if len(buf) >= size or ends_sentence:
            groups.append(buf)
            buf = []
    if buf:
        groups.append(buf)

    merged: list[list[dict]] = []
    for g in groups:
        if merged and len(g) < MIN_CAPTION_WORDS:
            merged[-1].extend(g)
        else:
            merged.append(g)

    out = [(g[0]["start"], g[-1]["end"], " ".join(x["word"] for x in g))
           for g in merged]
    for i in range(len(out) - 1):
        start, end, text = out[i]
        next_start = out[i + 1][0]
        if next_start - end <= MAX_CAPTION_GAP:
            out[i] = (start, next_start, text)
    return out


def emit_audio(name: str, target: float) -> None:
    """Silence-pad a beat's narration to the segment length, with edge fades."""
    run(["ffmpeg", "-y", "-i", str(VO / f"{name}.mp3"),
         "-af", (f"apad=whole_dur={target:.3f},"
                 f"afade=t=in:st=0:d=0.03,"
                 f"afade=t=out:st={max(target - 0.03, 0):.3f}:d=0.03"),
         "-t", f"{target:.3f}", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         str(SEG / f"{name}.m4a")])


def main() -> int:
    recordings = sorted(RAW.glob("*.webm"))
    if not recordings:
        raise SystemExit("no recording in demo/raw — run: node demo/drive.mjs --video")
    source = recordings[0]
    beats_file = RAW / "beats.json"
    if not beats_file.exists():
        raise SystemExit("demo/raw/beats.json missing — the recording run did not finish")

    beats = json.loads(beats_file.read_text())
    timings = json.loads((VO / "timings.json").read_text())

    src_duration = probe_duration(source)
    shutil.rmtree(SEG, ignore_errors=True)
    SEG.mkdir(parents=True, exist_ok=True)

    # Beat windows in the source recording. The last beat runs to end of file.
    windows = []
    for i, b in enumerate(beats):
        end = beats[i + 1]["t"] if i + 1 < len(beats) else src_duration
        windows.append((b["name"], b["t"], min(end, src_duration)))

    win_by_name = {name: (start, end) for name, start, end in windows}

    subtitle_entries: list[tuple[float, float, str]] = []
    concat_lines: list[str] = []
    audio_inputs: list[Path] = []
    timeline = 0.0
    last_window: tuple[float, float] | None = None

    # Iterate in NARRATION order, not recording order. The agent decides when to
    # close, so it can end a turn early and leave a scripted beat with no footage
    # of its own. That narration still has to play, over a held frame of whatever
    # was last on screen, rather than being silently dropped.
    for vo in timings:
        name = vo["beat"]
        target = vo["duration"] + TAIL_PAD
        seg = SEG / f"{name}.mp4"

        if name not in win_by_name:
            if last_window is None:
                print(f"{name:20s} SKIPPED — no footage and nothing preceding it")
                continue
            freeze_at = max(last_window[1] - 0.15, last_window[0])
            print(f"{name:20s} no footage -> holding frame at {freeze_at:6.2f}s")
            run(["ffmpeg", "-y", "-ss", f"{freeze_at:.3f}", "-i", str(source),
                 "-frames:v", "1", "-q:v", "2", str(SEG / f"{name}.png")])
            run(["ffmpeg", "-y", "-loop", "1", "-i", str(SEG / f"{name}.png"),
                 "-t", f"{target:.3f}", "-an",
                 "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p",
                 "-c:v", "libx264", "-preset", "medium", "-crf", CRF,
                 "-pix_fmt", "yuv420p", "-r", str(FPS),
                 "-video_track_timescale", "90000", str(seg)])
            emit_audio(name, target)
            for ws, we, text in chunk_words(vo["words"], WORDS_PER_CAPTION):
                subtitle_entries.append((timeline + ws, timeline + we, text))
            concat_lines.append(f"file '{seg.as_posix()}'")
            audio_inputs.append(SEG / f"{name}.m4a")
            timeline += target
            continue

        start, end = win_by_name[name]
        last_window = (start, end)
        video_len = max(end - start, 0.1)

        if target > video_len:
            # Narration outlasts the action: play the slice, then hold its last
            # frame. tpad is frame-accurate and avoids a visible re-loop.
            vf = (f"tpad=stop_mode=clone:stop_duration={target - video_len:.3f},"
                  f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p")
        else:
            # Action outlasts the narration: keep the action, it is the point.
            target = video_len
            vf = f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p"

        # -ss/-t BEFORE -i bound what is read from the source; the -t after the
        # filters bounds the output. Both as output options would collide and the
        # slice would bleed into the next beat instead of freezing.
        run(["ffmpeg", "-y",
             "-ss", f"{start:.3f}", "-t", f"{video_len:.3f}", "-i", str(source),
             "-an", "-vf", vf, "-t", f"{target:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", CRF,
             "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-video_track_timescale", "90000", str(seg)])

        emit_audio(name, target)
        apad = SEG / f"{name}.m4a"

        for word_start, word_end, text in chunk_words(vo["words"], WORDS_PER_CAPTION):
            subtitle_entries.append((timeline + word_start, timeline + word_end, text))

        concat_lines.append(f"file '{seg.as_posix()}'")
        audio_inputs.append(apad)
        timeline += target
        print(f"{name:20s} video {video_len:6.2f}s -> segment {target:6.2f}s")

    video_list = EDIT / "segments.txt"
    video_list.write_text("\n".join(concat_lines) + "\n")
    audio_list = EDIT / "audio.txt"
    audio_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in audio_inputs) + "\n")

    silent = EDIT / "video_only.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(video_list),
         "-c", "copy", str(silent)])
    voice = EDIT / "voice.m4a"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list),
         "-c", "copy", str(voice)])

    # Render every caption card, then composite them in one pass.
    shutil.rmtree(CAPS, ignore_errors=True)
    CAPS.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    label = "0:v"
    for i, (start, end, text) in enumerate(subtitle_entries):
        png = CAPS / f"{i:04d}.png"
        _, h = render_caption(text, png)
        inputs += ["-i", str(png)]
        nxt = f"c{i}"
        filters.append(
            f"[{label}][{i + 1}:v]overlay=x=(W-w)/2:y=H-{CAP_BOTTOM}-{h}:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{nxt}]"
        )
        label = nxt
    print(f"compositing {len(subtitle_entries)} caption cards")

    # Subtitles are burned last, after audio is muxed — nothing can cover them.
    final = EDIT / "final.mp4"
    run(["ffmpeg", "-y", "-i", str(silent), *inputs, "-i", str(voice),
         "-filter_complex", ";".join(filters),
         "-map", f"[{label}]", "-map", f"{len(subtitle_entries) + 1}:a:0",
         "-c:v", "libx264", "-preset", "slow", "-crf", CRF, "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
         str(final)])

    print(f"\nfinal: {final}  {probe_duration(final):.1f}s  "
          f"{final.stat().st_size / 1e6:.1f} MB  ({len(subtitle_entries)} captions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
