#!/usr/bin/env python3
"""Phase 2A: Generate per-slide audio using Edge TTS with word-level timestamps.

Produces individual MP3 files, per-slide timestamp JSON files, a timing.json
with durations, and merged full-audio.mp3 / full-audio.wav files.

Usage:
    python3 generate_audio.py speech-script.json \
        --output-dir /tmp/workdir/audio \
        --timing-output /tmp/workdir/timing.json \
        --voice zh-CN-YunyangNeural
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys

import edge_tts


async def generate_slide_audio(slide_data: dict, output_dir: str, voice: str,
                                rate: str, pitch: str) -> dict:
    """Generate audio for a single slide with word-level timestamps."""
    idx = slide_data["slide"]
    text = slide_data["speech"]
    out_mp3 = os.path.join(output_dir, f"slide-{idx:02d}.mp3")
    out_json = os.path.join(output_dir, f"slide-{idx:02d}.json")

    # Skip if both mp3 and json already exist
    if (os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0
            and os.path.exists(out_json)):
        duration = get_duration(out_mp3)
        print(f"  Slide {idx}: {duration:.1f}s (cached) → {out_mp3}", flush=True)
        return {"slide": idx, "audio": out_mp3, "duration": duration}

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch,
                                       boundary="WordBoundary")
    words = []
    audio_chunks = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append({
                "text": chunk["text"],
                "offset_ms": chunk["offset"] / 10000,    # 100ns units → ms
                "duration_ms": chunk["duration"] / 10000,
            })

    # Write MP3 from collected audio chunks
    with open(out_mp3, "wb") as f:
        for audio_data in audio_chunks:
            f.write(audio_data)

    duration = get_duration(out_mp3)

    # Save word-level timestamps
    ts_data = {
        "slide": idx,
        "duration": duration,
        "words": words,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(ts_data, f, ensure_ascii=False, indent=2)

    print(f"  Slide {idx}: {duration:.1f}s, {len(words)} words → {out_mp3}", flush=True)
    return {"slide": idx, "audio": out_mp3, "duration": duration}


def get_duration(path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def concat_audio(timing: list, output_dir: str, workdir: str):
    """Merge all slide audio into full-audio.mp3 and full-audio.wav."""
    # Create concat list
    concat_path = os.path.join(workdir, "concat-audio.txt")
    with open(concat_path, "w") as f:
        for t in timing:
            f.write(f"file '{t['audio']}'\n")

    full_mp3 = os.path.join(workdir, "full-audio.mp3")
    full_wav = os.path.join(workdir, "full-audio.wav")

    # Always regenerate since audio may have been regenerated
    print("\n🔗 Merging into full-audio.mp3...", flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_path,
        "-c:a", "libmp3lame", "-ar", "44100", "-ac", "2",
        full_mp3,
    ], capture_output=True, check=True)

    print("🔄 Converting to full-audio.wav...", flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", full_mp3,
        "-ar", "16000", "-ac", "1",
        full_wav,
    ], capture_output=True, check=True)


async def main_async(args):
    with open(args.speech_script, encoding="utf-8") as f:
        slides = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"🔊 Generating {len(slides)} audio clips with word timestamps", flush=True)
    print(f"   Voice: {args.voice}, Rate: {args.rate}, Pitch: {args.pitch}", flush=True)

    results = []
    for slide in slides:
        result = await generate_slide_audio(slide, args.output_dir,
                                             args.voice, args.rate, args.pitch)
        results.append(result)

    # Save timing
    with open(args.timing_output, "w") as f:
        json.dump(results, f, indent=2)

    total = sum(r["duration"] for r in results)
    print(f"\n📊 Total duration: {total:.1f}s ({total/60:.1f} min)", flush=True)
    print(f"   Timing saved to: {args.timing_output}", flush=True)

    # Merge audio
    workdir = os.path.dirname(args.timing_output)
    concat_audio(results, args.output_dir, workdir)


def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio with timestamps")
    parser.add_argument("speech_script", help="Path to speech-script.json")
    parser.add_argument("--output-dir", required=True, help="Audio output directory")
    parser.add_argument("--timing-output", required=True, help="Timing JSON output path")
    parser.add_argument("--voice", default="zh-CN-YunyangNeural")
    parser.add_argument("--rate", default="-5%")
    parser.add_argument("--pitch", default="+0Hz")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
