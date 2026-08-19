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

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "demo" / "raw"
VO = ROOT / "demo" / "vo"
EDIT = ROOT / "demo" / "edit"
SEG = EDIT / "segments"

W, H, FPS = 1920, 1080, 30
CRF = "18"          # visually lossless for screen content
TAIL_PAD = 0.6      # seconds of held frame after each beat's narration ends

# YouTube-style captions: short chunks, sentence case, heavy outline, sat above
# the bottom edge so the composer bar stays readable underneath.
SUB_STYLE = (
    "FontName=Helvetica,FontSize=17,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&HC0000000,BackColour=&H00000000,"
    "BorderStyle=1,Outline=3,Shadow=1,"
    "Alignment=2,MarginV=48"
)
WORDS_PER_CAPTION = 6


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


def srt_time(t: float) -> str:
    if t < 0:
        t = 0.0
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{round((s % 1) * 1000):03d}"


def build_srt(entries: list[tuple[float, float, str]], path: Path) -> None:
    lines = []
    for i, (start, end, text) in enumerate(entries, 1):
        lines += [str(i), f"{srt_time(start)} --> {srt_time(end)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def chunk_words(words: list[dict], size: int) -> list[tuple[float, float, str]]:
    """Group words into caption cards, breaking early on sentence-final punctuation."""
    out, buf = [], []
    for w in words:
        buf.append(w)
        ends_sentence = w["word"].rstrip('"\')').endswith((".", "?", "!", ":"))
        if len(buf) >= size or ends_sentence:
            out.append((buf[0]["start"], buf[-1]["end"],
                        " ".join(x["word"] for x in buf)))
            buf = []
    if buf:
        out.append((buf[0]["start"], buf[-1]["end"], " ".join(x["word"] for x in buf)))
    return out


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
    vo_by_beat = {t["beat"]: t for t in timings}

    src_duration = probe_duration(source)
    shutil.rmtree(SEG, ignore_errors=True)
    SEG.mkdir(parents=True, exist_ok=True)

    # Beat windows in the source recording. The last beat runs to end of file.
    windows = []
    for i, b in enumerate(beats):
        end = beats[i + 1]["t"] if i + 1 < len(beats) else src_duration
        windows.append((b["name"], b["t"], min(end, src_duration)))

    subtitle_entries: list[tuple[float, float, str]] = []
    concat_lines: list[str] = []
    audio_inputs: list[Path] = []
    timeline = 0.0

    for name, start, end in windows:
        vo = vo_by_beat.get(name)
        if vo is None:
            continue
        video_len = max(end - start, 0.1)
        target = vo["duration"] + TAIL_PAD

        seg = SEG / f"{name}.mp4"
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

        # Silence-pad this beat's narration out to the segment length so the
        # audio track concatenates 1:1 with the video and never drifts.
        apad = SEG / f"{name}.m4a"
        run(["ffmpeg", "-y", "-i", str(VO / f"{name}.mp3"),
             "-af", (f"apad=whole_dur={target:.3f},"
                     f"afade=t=in:st=0:d=0.03,"
                     f"afade=t=out:st={max(target - 0.03, 0):.3f}:d=0.03"),
             "-t", f"{target:.3f}", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             str(apad)])

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

    srt = EDIT / "master.srt"
    build_srt(subtitle_entries, srt)

    # Subtitles are burned last, after audio is muxed — nothing can cover them.
    final = EDIT / "final.mp4"
    run(["ffmpeg", "-y", "-i", str(silent), "-i", str(voice),
         "-vf", f"subtitles='{srt.as_posix()}':force_style='{SUB_STYLE}'",
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "slow", "-crf", CRF, "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
         str(final)])

    print(f"\nfinal: {final}  {probe_duration(final):.1f}s  "
          f"{final.stat().st_size / 1e6:.1f} MB  ({len(subtitle_entries)} captions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
