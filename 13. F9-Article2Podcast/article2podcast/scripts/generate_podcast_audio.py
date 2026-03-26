#!/usr/bin/env python3
"""Phase 2: Generate per-turn audio using multi-speaker TTS.

Produces individual MP3 files for each dialogue turn with role-specific voices,
plus a timing.json with durations.

Usage:
    python3 generate_podcast_audio.py podcast-script.json \
        --output-dir audio/ \
        --timing-output timing.json \
        --host-voice zh-CN-YunxiNeural \
        --guest-voice zh-CN-XiaoyiNeural
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys

import edge_tts


VOICE_MAP = {}  # populated at runtime


async def generate_turn_audio(turn_data: dict, output_dir: str,
                               rate: str, pitch: str) -> dict:
    """Generate audio for a single dialogue turn."""
    idx = turn_data["turn"]
    role = turn_data["role"]
    text = turn_data["text"]
    voice = VOICE_MAP.get(role, "zh-CN-YunxiNeural")

    out_mp3 = os.path.join(output_dir, f"turn-{idx:02d}-{role}.mp3")
    out_json = os.path.join(output_dir, f"turn-{idx:02d}-{role}.json")

    # Skip if already exists
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0:
        duration = get_duration(out_mp3)
        print(f"  Turn {idx} ({role}): {duration:.1f}s (cached)", flush=True)
        return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio_chunks = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    with open(out_mp3, "wb") as f:
        for data in audio_chunks:
            f.write(data)

    duration = get_duration(out_mp3)
    print(f"  Turn {idx} ({role}): {duration:.1f}s → {out_mp3}", flush=True)
    return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}


def get_duration(path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


async def main_async(args):
    global VOICE_MAP
    VOICE_MAP = {
        "host": args.host_voice,
        "guest": args.guest_voice,
    }

    with open(args.podcast_script, encoding="utf-8") as f:
        turns = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"🔊 Generating {len(turns)} audio clips (multi-speaker)", flush=True)
    print(f"   Host voice:  {args.host_voice}", flush=True)
    print(f"   Guest voice: {args.guest_voice}", flush=True)

    results = []
    for turn in turns:
        result = await generate_turn_audio(
            turn, args.output_dir, args.rate, args.pitch
        )
        results.append(result)

    # Save timing
    with open(args.timing_output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total = sum(r["duration"] for r in results)
    print(f"\n📊 Total duration: {total:.1f}s ({total/60:.1f} min)", flush=True)
    print(f"   Timing saved to: {args.timing_output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Generate multi-speaker podcast audio")
    parser.add_argument("podcast_script", help="Path to podcast-script.json")
    parser.add_argument("--output-dir", required=True, help="Audio output directory")
    parser.add_argument("--timing-output", required=True, help="Timing JSON output path")
    parser.add_argument("--host-voice", default="zh-CN-XiaoxiaoNeural")
    parser.add_argument("--guest-voice", default="zh-CN-YunyangNeural")
    parser.add_argument("--rate", default="-5%")
    parser.add_argument("--pitch", default="+0Hz")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
