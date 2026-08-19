"""Generate the demo voiceover from demo/narration.json.

ElevenLabs' with-timestamps endpoint returns character-level alignment alongside
the audio, so the captions come from ground truth rather than from running ASR
over our own synthesised speech. One mp3 and one word-timing list per beat.

    ELEVENLABS_API_KEY=... python demo/voiceover.py

Writes demo/vo/<beat>.mp3 and demo/vo/timings.json.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo" / "vo"

# "Diana - Friendly and Polished", Indian accent, conversational.
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "f0JpDwzbGK384Dd1WH2s")
MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
API_KEY = os.getenv("ELEVENLABS_API_KEY", "")


def words_from_alignment(alignment: dict) -> list[dict]:
    """Collapse per-character timings into per-word ones.

    A word starts at the first character's start time and ends at the last
    character's end time. Whitespace separates words; punctuation stays attached
    so captions read naturally.
    """
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]

    words: list[dict] = []
    current, start, prev_end = "", None, 0.0
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if current:
                words.append({"word": current, "start": start, "end": prev_end})
                current, start = "", None
            continue
        if not current:
            start = s
        current += ch
        prev_end = e
    if current:
        words.append({"word": current, "start": start, "end": prev_end})
    return words


def synth(text: str, client: httpx.Client) -> tuple[bytes, list[dict], float]:
    r = client.post(
        f"/v1/text-to-speech/{VOICE_ID}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        json={
            "text": text,
            "model_id": MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                               "style": 0.0, "use_speaker_boost": True},
        },
    )
    if r.status_code != 200:
        raise SystemExit(f"ElevenLabs returned {r.status_code}: {r.text[:300]}")
    data = r.json()
    words = words_from_alignment(data["alignment"])
    duration = data["alignment"]["character_end_times_seconds"][-1]
    return base64.b64decode(data["audio_base64"]), words, duration


def main() -> int:
    if not API_KEY:
        raise SystemExit("Set ELEVENLABS_API_KEY")
    OUT.mkdir(parents=True, exist_ok=True)
    script = json.loads((ROOT / "demo" / "narration.json").read_text())

    timings = []
    total = 0.0
    with httpx.Client(base_url="https://api.elevenlabs.io", timeout=180,
                      headers={"xi-api-key": API_KEY}) as client:
        for item in script:
            beat = item["beat"]
            audio, words, duration = synth(item["text"], client)
            (OUT / f"{beat}.mp3").write_bytes(audio)
            timings.append({"beat": beat, "text": item["text"],
                            "duration": duration, "words": words})
            total += duration
            print(f"{beat:20s} {duration:6.2f}s  {len(words):3d} words")

    (OUT / "timings.json").write_text(json.dumps(timings, indent=2))
    print(f"\ntotal narration: {total:.1f}s ({total / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
