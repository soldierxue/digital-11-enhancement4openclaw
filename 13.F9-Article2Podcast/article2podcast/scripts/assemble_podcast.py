#!/usr/bin/env python3
"""Phase 3: Assemble individual turn audio clips into a complete podcast.

Concatenates audio clips with silence gaps between speaker turns,
optionally mixes in background music, and normalizes loudness.

Usage:
    python3 assemble_podcast.py timing.json \
        --output podcast.mp3 \
        --gap-ms 400 \
        --normalize
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def generate_silence(duration_ms: int, output_path: str):
    """Generate a silence audio file of given duration."""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", f"{duration_ms / 1000:.3f}",
        "-c:a", "libmp3lame", "-ar", "44100",
        output_path,
    ], capture_output=True, check=True)


def concat_with_gaps(timing: list, gap_ms: int, output_path: str):
    """Concatenate audio clips with silence gaps between turns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        silence_path = os.path.join(tmpdir, "silence.mp3")
        generate_silence(gap_ms, silence_path)

        # Build concat list
        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, "w") as f:
            for i, t in enumerate(timing):
                f.write(f"file '{os.path.abspath(t['audio'])}'\n")
                # Add silence between turns (not after last)
                if i < len(timing) - 1:
                    f.write(f"file '{os.path.abspath(silence_path)}'\n")

        # Concat
        raw_output = os.path.join(tmpdir, "raw-concat.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:a", "libmp3lame", "-ar", "44100", "-ac", "2",
            "-b:a", "192k",
            raw_output,
        ], capture_output=True, check=True)

        # Move to final output
        subprocess.run(["cp", raw_output, output_path], check=True)

    return output_path


def mix_bgm(podcast_path: str, bgm_path: str, bgm_volume: float, output_path: str):
    """Mix background music into the podcast at low volume."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", podcast_path,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex",
        f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=3[out]",
        "-map", "[out]",
        "-c:a", "libmp3lame", "-ar", "44100", "-b:a", "192k",
        output_path,
    ], capture_output=True, check=True)


def normalize_loudness(input_path: str, output_path: str, target_lufs: int = -16):
    """Normalize audio loudness to podcast standard (-16 LUFS)."""
    # First pass: measure loudness
    result = subprocess.run([
        "ffmpeg", "-i", input_path,
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ], capture_output=True, text=True)

    # Parse measured loudness from stderr
    stderr = result.stderr
    try:
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            measured = json.loads(stderr[json_start:json_end])
            input_i = measured.get("input_i", "-24")
            input_tp = measured.get("input_tp", "-2")
            input_lra = measured.get("input_lra", "7")
            input_thresh = measured.get("input_thresh", "-34")
        else:
            input_i, input_tp, input_lra, input_thresh = "-24", "-2", "7", "-34"
    except (json.JSONDecodeError, KeyError):
        input_i, input_tp, input_lra, input_thresh = "-24", "-2", "7", "-34"

    # Second pass: apply normalization
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-af", (
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:"
            f"measured_I={input_i}:measured_TP={input_tp}:"
            f"measured_LRA={input_lra}:measured_thresh={input_thresh}:"
            f"linear=true:print_format=summary"
        ),
        "-c:a", "libmp3lame", "-ar", "44100", "-b:a", "192k",
        output_path,
    ], capture_output=True, check=True)


def get_duration(path: str) -> float:
    """Get audio duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def main():
    parser = argparse.ArgumentParser(description="Assemble podcast audio")
    parser.add_argument("timing", help="Path to timing.json")
    parser.add_argument("--output", required=True, help="Output podcast MP3 path")
    parser.add_argument("--gap-ms", type=int, default=400,
                        help="Silence gap between turns (ms)")
    parser.add_argument("--bgm", default=None, help="Background music file path")
    parser.add_argument("--bgm-volume", type=float, default=0.08,
                        help="BGM volume (0.0-1.0)")
    parser.add_argument("--normalize", action="store_true",
                        help="Normalize loudness to -16 LUFS")
    parser.add_argument("--target-lufs", type=int, default=-16,
                        help="Target loudness in LUFS")
    args = parser.parse_args()

    with open(args.timing, encoding="utf-8") as f:
        timing = json.load(f)

    print(f"🎙️ Assembling {len(timing)} audio clips with {args.gap_ms}ms gaps", flush=True)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # Step 1: Concatenate with gaps
    concat_output = args.output + ".concat.mp3" if (args.bgm or args.normalize) else args.output
    concat_with_gaps(timing, args.gap_ms, concat_output)
    duration = get_duration(concat_output)
    print(f"   Concatenated: {duration:.1f}s ({duration/60:.1f} min)", flush=True)

    current_file = concat_output

    # Step 2: Mix BGM (optional)
    if args.bgm and os.path.exists(args.bgm):
        print(f"🎵 Mixing background music (volume={args.bgm_volume})...", flush=True)
        bgm_output = args.output + ".bgm.mp3" if args.normalize else args.output
        mix_bgm(current_file, args.bgm, args.bgm_volume, bgm_output)
        if current_file != args.output:
            os.remove(current_file)
        current_file = bgm_output

    # Step 3: Normalize loudness (optional)
    if args.normalize:
        print(f"📏 Normalizing loudness to {args.target_lufs} LUFS...", flush=True)
        normalize_loudness(current_file, args.output, args.target_lufs)
        if current_file != args.output:
            os.remove(current_file)
    elif current_file != args.output:
        os.rename(current_file, args.output)

    final_duration = get_duration(args.output)
    final_size_mb = os.path.getsize(args.output) / (1024 * 1024)
    print(f"✅ Podcast assembled: {final_duration:.1f}s ({final_duration/60:.1f} min), {final_size_mb:.1f} MB", flush=True)
    print(f"   Output: {args.output}", flush=True)


if __name__ == "__main__":
    main()
