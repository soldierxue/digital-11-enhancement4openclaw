#!/usr/bin/env python3
"""Phase 3: Generate subtitles from TTS word-level timestamps (primary)
or whisper.cpp (fallback).

Primary mode reads per-slide timestamp JSON files produced by generate_audio.py
and the original speech text to build accurate subtitles with zero transcription
errors.

Fallback: if TTS timestamp files are missing, runs whisper.cpp on full-audio.wav.

Usage:
    # Primary — from TTS timestamps:
    python3 extract_subtitles.py full-audio.wav \
        --output subtitles.json \
        --timing timing.json \
        --speech-script speech-script.json \
        --audio-dir audio/

    # Fallback flags (only used when TTS timestamps are absent):
        --whisper-binary ~/whisper.cpp/main \
        --whisper-model ~/whisper.cpp/models/ggml-small.bin
"""

import argparse
import json
import os
import re
import subprocess
import sys


# ---------------------------------------------------------------------------
# Primary: TTS timestamp-based subtitle generation
# ---------------------------------------------------------------------------

def load_tts_timestamps(audio_dir: str, num_slides: int) -> list | None:
    """Load per-slide TTS timestamp JSON files.

    Returns list of dicts or None if any file is missing.
    """
    timestamps = []
    for i in range(1, num_slides + 1):
        path = os.path.join(audio_dir, f"slide-{i:02d}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            timestamps.append(json.load(f))
    return timestamps


def load_speech_scripts(speech_script_path: str) -> dict:
    """Load speech scripts keyed by slide number."""
    with open(speech_script_path, encoding="utf-8") as f:
        slides = json.load(f)
    return {s["slide"]: s["speech"] for s in slides}


def align_words_with_punctuation(words: list, original_speech: str) -> list:
    """Align TTS word boundaries back to the original speech text to recover
    punctuation.

    Strategy: walk through original_speech char by char, matching word
    boundaries greedily. Characters between matched words are punctuation
    or whitespace — attach trailing punctuation to the preceding word.

    Returns a new word list where each word's text may include trailing
    punctuation from the original speech.
    """
    if not words or not original_speech:
        return words

    # Build a flat string from word texts to verify alignment
    enriched = []
    pos = 0  # position in original_speech

    for i, w in enumerate(words):
        w_text = w["text"]

        # Find this word in the original speech starting from pos
        idx = original_speech.find(w_text, pos)
        if idx == -1:
            # Try case-insensitive or partial match
            idx = original_speech.lower().find(w_text.lower(), pos)
        if idx == -1:
            # Can't find — use word as-is
            enriched.append(dict(w))
            continue

        # Collect any punctuation/space between the end of last match and this word
        # (These are pre-word chars — typically nothing or spaces)

        # After the word, collect trailing punctuation
        end_pos = idx + len(w_text)
        trailing = ""
        while end_pos < len(original_speech):
            ch = original_speech[end_pos]
            if ch in "，。！？；：、,.:;!?\u2014\u2026\u201c\u201d\u2018\u2019\"'""''…—":
                trailing += ch
                end_pos += 1
            else:
                break

        new_word = dict(w)
        new_word["text"] = w_text + trailing
        enriched.append(new_word)
        pos = end_pos

    return enriched


def generate_subtitles_from_tts(tts_timestamps: list, timing: list,
                                 speech_scripts: dict = None) -> list:
    """Build subtitles from TTS word-level timestamps + timing info.

    Strategy:
    1. If speech_scripts available, align words with original text to recover
       punctuation, then split at sentence-ending punctuation.
    2. Otherwise split purely by length.
    3. Each subtitle ≤ 40 Chinese characters.
    """
    # Build cumulative offset per slide (ms)
    slide_offsets = {}
    cumulative_ms = 0
    for t in timing:
        slide_offsets[t["slide"]] = cumulative_ms
        cumulative_ms += int(t["duration"] * 1000)

    sentence_end_chars = set("。！？；!?;")
    subtitles = []

    for ts in tts_timestamps:
        slide_num = ts["slide"]
        words = ts["words"]
        offset_base = slide_offsets.get(slide_num, 0)

        if not words:
            continue

        # Enrich words with punctuation from original speech if available
        if speech_scripts and slide_num in speech_scripts:
            words = align_words_with_punctuation(words, speech_scripts[slide_num])

        # Accumulate words into subtitle chunks
        current_text = ""
        chunk_start_ms = None
        chunk_end_ms = None

        for w in words:
            w_start = offset_base + w["offset_ms"]
            w_end = offset_base + w["offset_ms"] + w["duration_ms"]
            w_text = w["text"]

            if chunk_start_ms is None:
                chunk_start_ms = w_start

            current_text += w_text
            chunk_end_ms = w_end

            # Decide whether to flush
            is_sentence_end = len(w_text) > 0 and w_text[-1] in sentence_end_chars
            # Also check for comma-based splitting if getting long
            is_clause_end = (len(current_text) >= 20
                            and len(w_text) > 0
                            and w_text[-1] in "，,、")
            is_long = len(current_text) >= 40

            if is_sentence_end or is_long or is_clause_end:
                text = current_text.strip()
                if text:
                    subtitles.append({
                        "fromMs": int(chunk_start_ms),
                        "toMs": int(chunk_end_ms),
                        "text": text,
                        "slide": slide_num,
                    })
                current_text = ""
                chunk_start_ms = None
                chunk_end_ms = None

        # Flush remaining text for this slide
        if current_text.strip():
            # Try to merge very short remainders with previous subtitle
            text = current_text.strip()
            if (len(text) <= 6 and subtitles
                    and subtitles[-1]["slide"] == slide_num
                    and len(subtitles[-1]["text"]) + len(text) <= 45):
                subtitles[-1]["text"] += text
                subtitles[-1]["toMs"] = int(chunk_end_ms)
            else:
                subtitles.append({
                    "fromMs": int(chunk_start_ms),
                    "toMs": int(chunk_end_ms),
                    "text": text,
                    "slide": slide_num,
                })

    return subtitles


# ---------------------------------------------------------------------------
# Fallback: whisper.cpp-based subtitle extraction
# ---------------------------------------------------------------------------

def run_whisper(audio_path: str, whisper_binary: str, whisper_model: str) -> dict:
    """Run whisper.cpp and return parsed JSON output."""
    output_base = audio_path.rsplit(".", 1)[0]
    output_json = output_base + ".json"

    if os.path.exists(output_json):
        print(f"  Using cached whisper output: {output_json}", flush=True)
        with open(output_json, encoding="utf-8") as f:
            return json.load(f)

    cmd = [
        os.path.expanduser(whisper_binary),
        "-m", os.path.expanduser(whisper_model),
        "-l", "zh",
        "-oj",
        "-f", audio_path,
    ]

    print(f"  Running: {' '.join(cmd)}", flush=True)
    print(f"  ⏳ This may take ~8 minutes on ARM64...", flush=True)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ whisper.cpp failed: {result.stderr[:500]}", flush=True)
        sys.exit(1)

    if not os.path.exists(output_json):
        alt_json = audio_path + ".json"
        if os.path.exists(alt_json):
            output_json = alt_json
        else:
            print(f"  ❌ Output JSON not found at {output_json}", flush=True)
            sys.exit(1)

    with open(output_json, encoding="utf-8") as f:
        return json.load(f)


def parse_whisper_output(whisper_data: dict, timing: list) -> list:
    """Parse whisper.cpp JSON output and align to slide boundaries."""
    transcription = whisper_data.get("transcription", [])

    slide_boundaries = []
    cumulative_ms = 0
    for t in timing:
        start_ms = cumulative_ms
        end_ms = cumulative_ms + int(t["duration"] * 1000)
        slide_boundaries.append({
            "slide": t["slide"],
            "startMs": start_ms,
            "endMs": end_ms,
        })
        cumulative_ms = end_ms

    subtitles = []
    for segment in transcription:
        from_ms = segment["offsets"]["from"]
        to_ms = segment["offsets"]["to"]
        text = segment["text"].strip()

        if not text or len(text) < 2:
            continue

        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\[.*?\]", "", text)
        text = re.sub(r"\(.*?\)", "", text)
        text = text.strip()
        if not text:
            continue

        mid_ms = (from_ms + to_ms) / 2
        slide_num = 1
        for boundary in slide_boundaries:
            if boundary["startMs"] <= mid_ms <= boundary["endMs"]:
                slide_num = boundary["slide"]
                break

        if len(text) > 40:
            chunks = split_text(text, max_len=40)
            chunk_duration = (to_ms - from_ms) / len(chunks)
            for i, chunk in enumerate(chunks):
                subtitles.append({
                    "fromMs": int(from_ms + i * chunk_duration),
                    "toMs": int(from_ms + (i + 1) * chunk_duration),
                    "text": chunk,
                    "slide": slide_num,
                })
        else:
            subtitles.append({
                "fromMs": from_ms,
                "toMs": to_ms,
                "text": text,
                "slide": slide_num,
            })

    return subtitles


def split_text(text: str, max_len: int = 40) -> list:
    """Split text at punctuation boundaries, keeping chunks ≤max_len."""
    split_chars = "，。！？；、,."
    chunks = []
    current = ""

    for char in text:
        current += char
        if char in split_chars and len(current) >= 8:
            chunks.append(current.strip())
            current = ""

    if current.strip():
        if chunks and len(current.strip()) < 8:
            chunks[-1] += current.strip()
        else:
            chunks.append(current.strip())

    return chunks if chunks else [text]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate subtitles from TTS timestamps (primary) or whisper.cpp (fallback)")
    parser.add_argument("audio", help="Path to full-audio.wav")
    parser.add_argument("--output", required=True, help="Output subtitles.json path")
    parser.add_argument("--timing", required=True, help="Path to timing.json")
    parser.add_argument("--speech-script", default=None,
                        help="Path to speech-script.json (for punctuation recovery)")
    parser.add_argument("--audio-dir", default=None,
                        help="Directory containing slide-NN.json timestamp files")
    parser.add_argument("--whisper-binary", default="~/whisper.cpp/main")
    parser.add_argument("--whisper-model", default="~/whisper.cpp/models/ggml-small.bin")
    args = parser.parse_args()

    with open(args.timing, encoding="utf-8") as f:
        timing = json.load(f)

    num_slides = len(timing)

    # Determine audio-dir if not specified
    audio_dir = args.audio_dir
    if audio_dir is None:
        if timing and "audio" in timing[0]:
            audio_dir = os.path.dirname(timing[0]["audio"])
        else:
            audio_dir = os.path.join(os.path.dirname(args.output), "audio")

    # Try primary: TTS timestamps
    tts_timestamps = load_tts_timestamps(audio_dir, num_slides)

    if tts_timestamps is not None:
        print("📄 Generating subtitles from TTS word-level timestamps...", flush=True)

        # Load speech scripts for punctuation recovery
        speech_scripts = None
        speech_script_path = args.speech_script
        if speech_script_path is None:
            # Try to find it automatically
            candidate = os.path.join(os.path.dirname(args.output), "speech-script.json")
            if os.path.exists(candidate):
                speech_script_path = candidate
        if speech_script_path and os.path.exists(speech_script_path):
            speech_scripts = load_speech_scripts(speech_script_path)
            print(f"  Using speech script for punctuation recovery: {speech_script_path}",
                  flush=True)

        subtitles = generate_subtitles_from_tts(tts_timestamps, timing, speech_scripts)
        print(f"  ✅ Generated {len(subtitles)} subtitle entries from TTS timestamps",
              flush=True)
    else:
        print("⚠️  TTS timestamp files not found, falling back to whisper.cpp...",
              flush=True)
        whisper_data = run_whisper(args.audio, args.whisper_binary, args.whisper_model)
        print("🔄 Parsing and aligning subtitles...", flush=True)
        subtitles = parse_whisper_output(whisper_data, timing)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(subtitles, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(subtitles)} subtitle entries written to {args.output}", flush=True)


if __name__ == "__main__":
    main()
