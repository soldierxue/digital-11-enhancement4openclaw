#!/usr/bin/env python3
"""
批量重新生成所有已有播客的 TTS 音频（Phase 2 + Phase 3），使用新的音色策略。

功能：
1. 遍历所有已有 podcast workdir（含 podcast-script.json）
2. 清除旧 audio/ 目录和 timing.json（强制重新生成）
3. 使用 auto 模式（随机主持人 + 嘉宾优先级）生成新音频
4. 重新拼接为最终 MP3
5. 上传到 S3 覆盖旧文件
6. 完成后更新 RSS feed

断点恢复：通过 state file 跟踪进度，中断后从上次失败处继续。

用法：
  python3 scripts/regenerate_all_audio.py [--dry-run] [--start-from SLUG] [--delay 2]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
OUTPUT_DIR = os.path.join(WORKSPACE, "output")
STATE_FILE = os.path.join(SKILL_DIR, "regenerate-state.json")
S3_BUCKET = "claw2026"


def get_all_episode_slugs():
    """Get all published episode slugs (those with both mp3 and script)."""
    slugs = []
    for mp3 in sorted(os.listdir(OUTPUT_DIR)):
        if not mp3.endswith("-podcast.mp3"):
            continue
        slug = mp3.replace("-podcast.mp3", "")
        # Check if workdir with script exists
        # Handle truncated workdir names
        workdir = find_workdir(slug)
        if workdir and os.path.exists(os.path.join(workdir, "podcast-script.json")):
            slugs.append(slug)
    return slugs


def find_workdir(slug):
    """Find the workdir for a slug (handles truncated names)."""
    exact = os.path.join(WORKSPACE, f"podcast-{slug}")
    if os.path.isdir(exact):
        return exact
    # Try prefix match (workdir names may be truncated)
    for d in os.listdir(WORKSPACE):
        if d.startswith("podcast-") and slug.startswith(d.replace("podcast-", "")):
            return os.path.join(WORKSPACE, d)
        if d.startswith("podcast-") and d.replace("podcast-", "").startswith(slug[:40]):
            # Check if the script matches
            candidate = os.path.join(WORKSPACE, d)
            if os.path.exists(os.path.join(candidate, "podcast-script.json")):
                return candidate
    return None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": [], "current": None, "started": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def regenerate_episode(slug, workdir, delay_between_turns=2):
    """Regenerate audio for a single episode."""
    audio_dir = os.path.join(workdir, "audio")
    timing_path = os.path.join(workdir, "timing.json")
    script_path = os.path.join(workdir, "podcast-script.json")
    final_mp3 = os.path.join(OUTPUT_DIR, f"{slug}-podcast.mp3")

    # 1. Clear old audio cache to force regeneration
    if os.path.isdir(audio_dir):
        shutil.rmtree(audio_dir)
        print(f"  🗑️  Cleared old audio/", flush=True)
    os.makedirs(audio_dir, exist_ok=True)

    if os.path.exists(timing_path):
        os.remove(timing_path)

    # 2. Run Phase 2: TTS generation with auto mode
    cmd_phase2 = [
        sys.executable,
        os.path.join(SKILL_DIR, "scripts", "generate_podcast_audio.py"),
        script_path,
        "--output-dir", audio_dir,
        "--timing-output", timing_path,
        "--tts-backend", "auto",
    ]

    print(f"  🔊 Phase 2: Generating audio (auto mode)...", flush=True)
    result = subprocess.run(cmd_phase2, capture_output=True, text=True, timeout=1800)

    if result.returncode != 0:
        print(f"  ❌ Phase 2 failed: {result.stderr[-300:]}", flush=True)
        return False

    # Print TTS selection info
    for line in result.stdout.split("\n"):
        if "🎲" in line or "🎤" in line or "Total duration" in line or "降级" in line:
            print(f"  {line.strip()}", flush=True)

    # 3. Run Phase 3: Assembly
    cmd_phase3 = [
        sys.executable,
        os.path.join(SKILL_DIR, "scripts", "assemble_podcast.py"),
        timing_path,
        "--output", final_mp3,
        "--gap-ms", "400",
        "--normalize",
    ]

    print(f"  🎙️ Phase 3: Assembling podcast...", flush=True)
    result = subprocess.run(cmd_phase3, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        print(f"  ❌ Phase 3 failed: {result.stderr[-200:]}", flush=True)
        return False

    # Check output
    if not os.path.exists(final_mp3):
        print(f"  ❌ No output MP3", flush=True)
        return False

    size_mb = os.path.getsize(final_mp3) / (1024 * 1024)
    duration = get_duration(final_mp3)
    print(f"  ✅ Done: {duration:.0f}s ({size_mb:.1f}MB)", flush=True)

    # 4. Upload to S3
    print(f"  📤 Uploading to S3...", flush=True)
    s3_result = subprocess.run(
        ["aws", "s3", "cp", final_mp3, f"s3://{S3_BUCKET}/podcast/episodes/{slug}.mp3"],
        capture_output=True, text=True, timeout=120,
    )
    if s3_result.returncode != 0:
        print(f"  ⚠️  S3 upload failed: {s3_result.stderr[:100]}", flush=True)
    else:
        print(f"  📤 S3 uploaded", flush=True)

    return True


def get_duration(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except:
        pass
    return 0.0


def main():
    parser = argparse.ArgumentParser(description="Regenerate all podcast audio with new voices")
    parser.add_argument("--dry-run", action="store_true", help="List episodes without processing")
    parser.add_argument("--start-from", help="Start from this slug (skip earlier ones)")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between episodes (default 2)")
    parser.add_argument("--resume", action="store_true", help="Resume from state file")
    args = parser.parse_args()

    slugs = get_all_episode_slugs()
    print(f"📋 Found {len(slugs)} published episodes\n", flush=True)

    if args.dry_run:
        for i, slug in enumerate(slugs, 1):
            workdir = find_workdir(slug)
            script = os.path.join(workdir, "podcast-script.json") if workdir else "?"
            turns = 0
            if workdir and os.path.exists(os.path.join(workdir, "podcast-script.json")):
                with open(os.path.join(workdir, "podcast-script.json")) as f:
                    turns = len(json.load(f))
            print(f"  {i:2d}. {slug} ({turns} turns)")
        return

    state = load_state() if args.resume else {"completed": [], "failed": [], "current": None, "started": datetime.now().isoformat()}

    # Apply start-from filter
    start_idx = 0
    if args.start_from:
        for i, s in enumerate(slugs):
            if args.start_from in s:
                start_idx = i
                break

    if args.resume and state.get("completed"):
        # Skip already completed
        completed_set = set(state["completed"])
        remaining = [s for s in slugs if s not in completed_set]
        print(f"📋 Resuming: {len(state['completed'])} done, {len(remaining)} remaining\n", flush=True)
    else:
        remaining = slugs[start_idx:]

    total = len(remaining)
    for i, slug in enumerate(remaining, 1):
        workdir = find_workdir(slug)
        if not workdir:
            print(f"\n[{i}/{total}] ⏭️  {slug}: no workdir found, skipping", flush=True)
            state["failed"].append(slug)
            save_state(state)
            continue

        print(f"\n{'='*60}", flush=True)
        print(f"[{i}/{total}] 🎙️ {slug}", flush=True)
        print(f"{'='*60}", flush=True)

        state["current"] = slug
        save_state(state)

        success = regenerate_episode(slug, workdir)

        if success:
            state["completed"].append(slug)
            state["current"] = None
        else:
            state["failed"].append(slug)
            state["current"] = None

        save_state(state)

        # Delay between episodes
        if i < total:
            print(f"  ⏳ Waiting {args.delay}s before next episode...", flush=True)
            time.sleep(args.delay)

    # Summary
    print(f"\n{'='*60}", flush=True)
    print(f"📊 Regeneration complete!", flush=True)
    print(f"   ✅ Success: {len(state['completed'])}", flush=True)
    print(f"   ❌ Failed: {len(state['failed'])}", flush=True)
    if state["failed"]:
        print(f"   Failed slugs:", flush=True)
        for s in state["failed"]:
            print(f"     - {s}", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    main()
