#!/usr/bin/env python3
"""Phase 4 prep: Assemble data.json and copy assets into Remotion public/ directory.

This script prepares everything Remotion needs to render the video:
1. Builds data.json from timing + subtitles + slide metadata
2. Copies images and audio into remotion-template/public/
3. Copies the full merged audio

Usage:
    python3 prepare_remotion.py \
        --workdir /tmp/article2video-slug \
        --remotion-dir ~/.openclaw/skills/article2video/remotion-template \
        --timing timing.json \
        --subtitles subtitles.json \
        --speech-script speech-script.json \
        --style photo \
        --fps 30 --width 1920 --height 1080
"""

import argparse
import json
import os
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description="Prepare Remotion data and assets")
    parser.add_argument("--workdir", required=True, help="Pipeline working directory")
    parser.add_argument("--remotion-dir", required=True, help="Remotion template directory")
    parser.add_argument("--timing", required=True, help="Path to timing.json")
    parser.add_argument("--subtitles", required=True, help="Path to subtitles.json")
    parser.add_argument("--speech-script", required=True, help="Path to speech-script.json")
    parser.add_argument("--style", default="photo", choices=["photo", "ai"])
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--format", default="landscape", choices=["landscape", "portrait", "both"],
                        help="Video format (landscape/portrait/both)")
    args = parser.parse_args()

    public_dir = os.path.join(args.remotion_dir, "public")
    os.makedirs(public_dir, exist_ok=True)

    # Load data
    with open(args.timing, encoding="utf-8") as f:
        timing = json.load(f)
    with open(args.subtitles, encoding="utf-8") as f:
        subtitles = json.load(f)
    with open(args.speech_script, encoding="utf-8") as f:
        speech_script = json.load(f)

    images_dir = os.path.join(args.workdir, "images")
    audio_dir = os.path.join(args.workdir, "audio")

    # Build slide data with cumulative timing
    slides = []
    cumulative_ms = 0
    total_duration_ms = 0

    for i, t in enumerate(timing):
        idx = t["slide"]
        duration_ms = int(t["duration"] * 1000)
        start_ms = cumulative_ms
        end_ms = cumulative_ms + duration_ms

        # Determine image filename
        if args.style == "ai":
            img_file = f"slide-{idx:02d}.png"
        else:
            img_file = f"slide-{idx:02d}.jpg"

        # Audio filename
        audio_file = f"slide-{idx:02d}.mp3"

        # Get title from speech script
        title = ""
        key_facts = None
        if i < len(speech_script):
            title = speech_script[i].get("title", f"Slide {idx}")
            key_facts = speech_script[i].get("key_facts", None)

        slide_data = {
            "slide": idx,
            "startMs": start_ms,
            "endMs": end_ms,
            "image": img_file,
            "audio": audio_file,
            "title": title,
        }
        if key_facts:
            slide_data["key_facts"] = key_facts

        slides.append(slide_data)

        cumulative_ms = end_ms
        total_duration_ms = end_ms

    # Assemble data.json
    data = {
        "totalDurationMs": total_duration_ms,
        "fps": args.fps,
        "width": args.width,
        "height": args.height,
        "format": args.format,
        "slides": slides,
        "subtitles": subtitles,
        "branding": "",
        "avatarFrames": 302,
    }

    # Write data.json to public/
    data_path = os.path.join(public_dir, "data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"📋 data.json written ({total_duration_ms/1000:.1f}s, {len(slides)} slides)", flush=True)

    # Copy images
    print(f"🖼️ Copying images to public/...", flush=True)
    for slide in slides:
        src = os.path.join(images_dir, slide["image"])
        dst = os.path.join(public_dir, slide["image"])
        if os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            print(f"  ⚠️ Missing image: {src}", flush=True)

    # Copy per-slide audio
    print(f"🔊 Copying audio files to public/...", flush=True)
    for slide in slides:
        src = os.path.join(audio_dir, slide["audio"])
        dst = os.path.join(public_dir, slide["audio"])
        if os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            print(f"  ⚠️ Missing audio: {src}", flush=True)

    # Copy full merged audio
    full_mp3_src = os.path.join(args.workdir, "full-audio.mp3")
    full_mp3_dst = os.path.join(public_dir, "full-audio.mp3")
    if os.path.exists(full_mp3_src):
        shutil.copy2(full_mp3_src, full_mp3_dst)
        print(f"🔊 full-audio.mp3 copied", flush=True)
    else:
        print(f"  ⚠️ Missing full-audio.mp3!", flush=True)

    # Copy animated avatar frames (PNG sequence)
    avatar_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "assets", "avatar-animated-frames")
    avatar_dst_dir = os.path.join(public_dir, "avatar")
    if os.path.isdir(avatar_src_dir):
        os.makedirs(avatar_dst_dir, exist_ok=True)
        # Only copy if not already present (fast skip)
        existing = set(os.listdir(avatar_dst_dir)) if os.path.isdir(avatar_dst_dir) else set()
        src_frames = sorted([f for f in os.listdir(avatar_src_dir) if f.endswith('.png')])
        copied = 0
        for f in src_frames:
            if f not in existing:
                shutil.copy2(os.path.join(avatar_src_dir, f), os.path.join(avatar_dst_dir, f))
                copied += 1
        print(f"🎭 Animated avatar: {len(src_frames)} frames ({copied} newly copied)", flush=True)
        data["avatarFrames"] = len(src_frames)
        # Re-write data.json with updated avatarFrames count
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        # Fallback: copy static presenter if no animated frames
        presenter_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "assets", "avatar", "presenter-half-nobg.png")
        presenter_dst = os.path.join(public_dir, "presenter-half.png")
        if os.path.exists(presenter_src):
            shutil.copy2(presenter_src, presenter_dst)
            print(f"🎭 Static avatar fallback: presenter-half.png copied", flush=True)
        else:
            print(f"  ⚠️ No avatar assets found!", flush=True)

    print(f"✅ Remotion assets prepared in {public_dir}", flush=True)


if __name__ == "__main__":
    main()
