#!/usr/bin/env python3
"""Phase 5: Compress video to target size using FFmpeg 2-pass VBR.

Usage:
    python3 compress_video.py input.mp4 \
        --output compressed.mp4 \
        --target-mb 20 \
        --video-bitrate 280k \
        --audio-bitrate 96k
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def get_video_info(path: str) -> dict:
    """Get video duration and size using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries",
         "format=duration,size", "-of", "json", path],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)["format"]
    return {
        "duration": float(info["duration"]),
        "size_mb": int(info["size"]) / (1024 * 1024),
    }


def compress_2pass(input_path: str, output_path: str,
                   video_bitrate: str, audio_bitrate: str):
    """2-pass VBR compression."""
    passlog = tempfile.mktemp(prefix="ffmpeg2pass")

    # Pass 1
    print("  Pass 1/2...", flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-b:v", video_bitrate,
        "-preset", "medium", "-pass", "1",
        "-passlogfile", passlog,
        "-an", "-f", "null", "/dev/null",
    ], capture_output=True, check=True)

    # Pass 2
    print("  Pass 2/2...", flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-b:v", video_bitrate,
        "-preset", "medium", "-pass", "2",
        "-passlogfile", passlog,
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        output_path,
    ], capture_output=True, check=True)

    # Clean up passlog files
    for suffix in ["-0.log", "-0.log.mbtree", ".log", ".log.mbtree"]:
        path = passlog + suffix
        if os.path.exists(path):
            os.remove(path)


def main():
    parser = argparse.ArgumentParser(description="Compress video with FFmpeg")
    parser.add_argument("input", help="Input video path")
    parser.add_argument("--output", required=True, help="Output path")
    parser.add_argument("--target-mb", type=float, default=20, help="Target size in MB")
    parser.add_argument("--video-bitrate", default="280k", help="Video bitrate")
    parser.add_argument("--audio-bitrate", default="96k", help="Audio bitrate")
    args = parser.parse_args()

    input_info = get_video_info(args.input)
    print(f"📦 Input: {input_info['size_mb']:.1f} MB, {input_info['duration']:.1f}s", flush=True)

    if input_info["size_mb"] <= args.target_mb:
        print(f"  Already ≤{args.target_mb}MB, copying directly.", flush=True)
        shutil.copy2(args.input, args.output)
    else:
        # Calculate optimal bitrate if needed
        duration_s = input_info["duration"]
        target_bytes = args.target_mb * 1024 * 1024
        # Reserve ~12% for audio
        audio_bytes = duration_s * 12000  # ~96kbps
        video_bytes = target_bytes - audio_bytes
        calculated_bitrate = int(video_bytes * 8 / duration_s)
        # Use the lower of specified and calculated bitrate
        specified_bps = parse_bitrate(args.video_bitrate)
        actual_bps = min(specified_bps, calculated_bitrate) if calculated_bitrate > 0 else specified_bps
        actual_bitrate = f"{actual_bps // 1000}k"

        print(f"  Target: ≤{args.target_mb}MB", flush=True)
        print(f"  Video bitrate: {actual_bitrate} (calculated: {calculated_bitrate//1000}k)", flush=True)
        print(f"  Audio bitrate: {args.audio_bitrate}", flush=True)

        compress_2pass(args.input, args.output, actual_bitrate, args.audio_bitrate)

    output_info = get_video_info(args.output)
    print(f"✅ Output: {output_info['size_mb']:.1f} MB, {output_info['duration']:.1f}s", flush=True)

    if output_info["size_mb"] > args.target_mb:
        print(f"  ⚠️ Still above target ({output_info['size_mb']:.1f} > {args.target_mb}MB)", flush=True)
        print(f"     Consider lowering --video-bitrate", flush=True)


def parse_bitrate(bitrate_str: str) -> int:
    """Parse bitrate string like '280k' to bps."""
    bitrate_str = bitrate_str.strip().lower()
    if bitrate_str.endswith("k"):
        return int(bitrate_str[:-1]) * 1000
    elif bitrate_str.endswith("m"):
        return int(float(bitrate_str[:-1]) * 1000000)
    return int(bitrate_str)

if __name__ == "__main__":
    main()
