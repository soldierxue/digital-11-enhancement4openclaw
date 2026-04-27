#!/usr/bin/env python3
"""Reclone a MiniMax voice using a clean audio sample (no greeting/intro).

The MiniMax clone voice API learns from the prompt_audio sample. If that
sample contains a greeting like "欢迎收听本期播客...", the cloned voice
will prepend it to every synthesized segment (training data leakage).

This script:
  1. Takes a clean audio sample (pure speech, no intro/outro)
  2. If audio < 10s, loops it to meet the 10s minimum for clone source
  3. Reclones the voice with a new voice_id
  4. Runs a validation test to confirm no leakage

API reference: https://platform.minimaxi.com/docs/guides/speech-voice-clone
Endpoint: api.minimaxi.com

Audio sample requirements:
  - Format: mp3, m4a, or wav
  - Duration: at least 5s (will be looped to 10s+ if needed)
  - Content: Pure speech, NO greetings, intros, or outros
  - Quality: Clean recording, minimal background noise

Usage:
    # Basic: reclone with default settings
    python3 reclone_voice.py

    # Custom audio and voice ID
    python3 reclone_voice.py --audio /path/to/clean.m4a \\
        --voice-id my_custom_voice_003 \\
        --prompt-text "对应音频的文字转录"
"""

import argparse
import json
import os
import subprocess
import sys
import time

import requests

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_AUDIO = os.path.join(SKILL_DIR, "assets", "bgm", "jason_voice_prompt_5s.m4a")

UPLOAD_URL = "https://api.minimaxi.com/v1/files/upload"
CLONE_URL = "https://api.minimaxi.com/v1/voice_clone"


def load_credentials():
    with open(os.path.join(SKILL_DIR, "credentials.json")) as f:
        return json.load(f)


def load_config():
    with open(os.path.join(SKILL_DIR, "config.json")) as f:
        return json.load(f)


def get_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def upload_file(api_key, filepath, purpose):
    """Upload a file to MiniMax and return the file_id."""
    with open(filepath, "rb") as f:
        resp = requests.post(
            UPLOAD_URL, headers={"Authorization": "Bearer %s" % api_key},
            data={"purpose": purpose},
            files={"file": (os.path.basename(filepath), f)},
            timeout=60)
    resp.raise_for_status()
    result = resp.json()
    sc = result.get("base_resp", {}).get("status_code", -1)
    if sc != 0:
        raise RuntimeError("Upload failed: %s" % json.dumps(result, ensure_ascii=False))
    fid = result["file"]["file_id"]
    print("  Uploaded %s -> file_id=%s" % (os.path.basename(filepath), fid), flush=True)
    return fid


def ensure_min_duration(audio_path, min_seconds=10):
    """If audio is shorter than min_seconds, loop it to reach the minimum.
    Returns path to the (possibly looped) file."""
    dur = get_duration(audio_path)
    if dur >= min_seconds:
        return audio_path

    loops = int(min_seconds / dur) + 1
    ext = os.path.splitext(audio_path)[1]
    looped = "/tmp/reclone_looped%s" % ext
    concat_list = "/tmp/reclone_concat.txt"
    with open(concat_list, "w") as f:
        for _ in range(loops):
            f.write("file '%s'\n" % os.path.abspath(audio_path))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", looped],
        capture_output=True, check=True)
    new_dur = get_duration(looped)
    print("  Looped %s: %.1fs -> %.1fs (%dx)" % (os.path.basename(audio_path), dur, new_dur, loops), flush=True)
    return looped


def estimate_duration(text):
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return cjk / 4.5 + (len(text) - cjk) / 10.0


def main():
    parser = argparse.ArgumentParser(description="Reclone MiniMax voice with clean audio")
    parser.add_argument("--audio", default=DEFAULT_AUDIO,
                        help="Path to clean audio sample (default: assets/bgm/jason_voice_prompt_5s.m4a)")
    parser.add_argument("--voice-id", default="jason_podcast_voice_002",
                        help="New voice ID (default: jason_podcast_voice_002)")
    parser.add_argument("--prompt-text", default="大家好，我是薛以致用",
                        help="Transcript of the prompt audio")
    parser.add_argument("--test-text",
                        default="Anthropic在TPU上可以达到大约百分之四十的利用率，这个数据很说明问题。",
                        help="Text for post-clone validation")
    parser.add_argument("--update-config", action="store_true",
                        help="Auto-update config.json with new voice_id on success")
    args = parser.parse_args()

    creds = load_credentials()
    config = load_config()
    api_key = creds.get("minimax_api_key_clone") or creds["minimax_api_key"]
    group_id = creds["minimax_group_id"]
    model = config.get("minimax_model", "speech-2.8-hd")
    tts_url = "https://api.minimaxi.com/v1/t2a_v2?GroupId=%s" % group_id
    auth = {"Authorization": "Bearer %s" % api_key}

    print("=" * 60, flush=True)
    print("MiniMax Voice Reclone", flush=True)
    print("  Audio:    %s" % args.audio, flush=True)
    print("  Voice ID: %s" % args.voice_id, flush=True)
    print("  Model:    %s" % model, flush=True)
    print("=" * 60, flush=True)

    # Step 1: Prepare clone source (must be >= 10s)
    print("\nStep 1: Preparing clone source...", flush=True)
    clone_src = ensure_min_duration(args.audio, min_seconds=10)
    print("  Clone source: %.1fs" % get_duration(clone_src), flush=True)

    # Step 2: Upload files
    print("\nStep 2: Uploading files...", flush=True)
    clone_file_id = upload_file(api_key, clone_src, "voice_clone")

    # Use original (short) audio as prompt
    prompt_file_id = upload_file(api_key, args.audio, "prompt_audio")

    # Step 3: Clone
    print("\nStep 3: Cloning voice '%s'..." % args.voice_id, flush=True)
    clone_payload = {
        "file_id": clone_file_id,
        "voice_id": args.voice_id,
        "clone_prompt": {
            "prompt_audio": prompt_file_id,
            "prompt_text": args.prompt_text,
        },
        "model": model,
    }
    resp = requests.post(
        CLONE_URL,
        headers=dict(auth, **{"Content-Type": "application/json"}),
        json=clone_payload, timeout=120)
    resp.raise_for_status()
    result = resp.json()
    sc = result.get("base_resp", {}).get("status_code", -1)
    sm = result.get("base_resp", {}).get("status_msg", "")
    demo = result.get("demo_audio", "")

    print("  Status: %d (%s)" % (sc, sm), flush=True)
    if demo:
        print("  Demo: %s" % demo, flush=True)
    if sc != 0:
        print("\n❌ Clone FAILED: %s" % json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        sys.exit(1)

    print("\n✅ Clone successful!", flush=True)

    # Step 4: Validation test
    print("\nStep 4: Testing for leakage...", flush=True)
    time.sleep(3)

    resp = requests.post(
        tts_url,
        headers=dict(auth, **{"Content-Type": "application/json"}),
        json={
            "model": model, "text": args.test_text, "stream": False,
            "voice_setting": {"voice_id": args.voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "format": "mp3"},
        }, timeout=120)
    resp.raise_for_status()
    audio_hex = resp.json().get("data", {}).get("audio", "")
    if not audio_hex:
        print("  ❌ TTS test failed: no audio returned", flush=True)
        sys.exit(1)

    test_out = "/tmp/reclone_test_%s.mp3" % args.voice_id
    with open(test_out, "wb") as f:
        f.write(bytes.fromhex(audio_hex))

    actual = get_duration(test_out)
    expected = estimate_duration(args.test_text)
    excess = actual - expected

    print("  Test text: %s" % args.test_text, flush=True)
    print("  Expected: ~%.1fs" % expected, flush=True)
    print("  Actual:   %.1fs" % actual, flush=True)
    print("  Excess:   %+.1fs" % excess, flush=True)
    print("  Audio:    %s (listen to verify)" % test_out, flush=True)

    if excess > 5.0:
        print("\n⚠️  WARNING: New voice still has leakage (excess %.1fs)!" % excess, flush=True)
        print("  Try a cleaner audio sample with pure speech only.", flush=True)
        sys.exit(1)

    print("\n✅ Voice is CLEAN! No leakage detected.", flush=True)

    # Step 5: Optionally update config.json
    if args.update_config:
        config_path = os.path.join(SKILL_DIR, "config.json")
        config["guest_voice"]["primary"]["voice_id"] = args.voice_id
        config["guest_voice"]["primary"]["label"] = "MiniMax 薛以致用（克隆v2）"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print("\n📝 Updated config.json: guest_voice.primary.voice_id -> '%s'" % args.voice_id, flush=True)
    else:
        print("\n💡 To use this voice, run with --update-config or manually update config.json:", flush=True)
        print('   guest_voice.primary.voice_id: "%s"' % args.voice_id, flush=True)


if __name__ == "__main__":
    main()
