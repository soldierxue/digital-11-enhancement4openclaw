#!/usr/bin/env python3
"""Article2Podcast — 博客文章→多人对话播客 管道编排

将博客文章自动转换为双人对话播客音频。
Phase 1: 文章 → 对话脚本（LLM）
Phase 2: 对话脚本 → 多角色音频（TTS）
Phase 3: 音频拼接 + 后处理（FFmpeg）
Phase 4: 元数据生成（标题/描述/章节）

Usage:
    python3 main.py <article_path_or_url> [options]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")


def load_config() -> dict:
    config_path = os.path.join(SKILL_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def slugify(text: str) -> str:
    """Create a filesystem-safe slug from text."""
    text = os.path.splitext(text)[0]
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:60] or "podcast"


def ensure_workdir(slug: str) -> str:
    workdir = os.path.expanduser(f"~/.openclaw/workspace/podcast-{slug}")
    os.makedirs(workdir, exist_ok=True)
    return workdir


def run_script(script_name: str, args: list, cwd: str = None) -> subprocess.CompletedProcess:
    """Run a script from the scripts/ directory."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path] + [str(a) for a in args]
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"❌ Script {script_name} failed with code {result.returncode}", flush=True)
        sys.exit(1)
    return result


def main():
    parser = argparse.ArgumentParser(description="Article2Podcast pipeline")
    parser.add_argument("article", help="Path to Markdown file or URL")
    parser.add_argument("--host-voice", default=None,
                        help="TTS voice for host (default: from config)")
    parser.add_argument("--guest-voice", default=None,
                        help="TTS voice for guest (default: from config)")
    parser.add_argument("--turns", type=int, default=None,
                        help="Number of dialogue turns (default: from config)")
    parser.add_argument("--tts-backend", choices=["edge-tts", "minimax", "vibevoice"],
                        default=None, help="TTS backend (default: from config)")
    parser.add_argument("--bgm", default=None,
                        help="Background music file path")
    parser.add_argument("--bgm-volume", type=float, default=None,
                        help="BGM volume 0.0-1.0 (default: from config)")
    parser.add_argument("--no-normalize", action="store_true",
                        help="Skip loudness normalization")
    parser.add_argument("--skip-metadata", action="store_true",
                        help="Skip Phase 4 metadata generation")
    args = parser.parse_args()

    cfg = load_config()
    host_voice = args.host_voice or cfg.get("default_host_voice", "zh-CN-YunxiNeural")
    guest_voice = args.guest_voice or cfg.get("default_guest_voice", "zh-CN-XiaoyiNeural")
    turns = args.turns or cfg.get("default_turns", 20)
    tts_backend = args.tts_backend or cfg.get("default_tts_backend", "edge-tts")
    bgm_volume = args.bgm_volume if args.bgm_volume is not None else cfg.get("bgm_volume", 0.08)
    gap_ms = cfg.get("gap_ms", 400)

    slug = slugify(os.path.basename(args.article))
    workdir = ensure_workdir(slug)
    output_dir = os.path.expanduser(cfg.get("output_dir", "~/.openclaw/workspace/output"))
    os.makedirs(output_dir, exist_ok=True)

    final_podcast = os.path.join(output_dir, f"{slug}-podcast.mp3")
    final_metadata = os.path.join(output_dir, f"{slug}-metadata.json")

    start_time = time.time()
    print(f"""
╔══════════════════════════════════════════════════════════╗
║              Article2Podcast Pipeline                    ║
╠══════════════════════════════════════════════════════════╣
║  Article  : {args.article[:44]:<44s} ║
║  Turns    : {str(turns):<44s} ║
║  Host     : {host_voice:<44s} ║
║  Guest    : {guest_voice:<44s} ║
║  TTS      : {tts_backend:<44s} ║
║  Workdir  : {workdir[:44]:<44s} ║
║  Output   : {final_podcast[:44]:<44s} ║
╚══════════════════════════════════════════════════════════╝
""", flush=True)

    # ------------------------------------------------------------------
    # Phase 1: Article → Dialogue Script
    # ------------------------------------------------------------------
    podcast_script = os.path.join(workdir, "podcast-script.json")
    if os.path.exists(podcast_script):
        print(f"✅ Phase 1: podcast-script.json already exists, skipping.", flush=True)
    else:
        print("📝 Phase 1: Generating dialogue script from article...", flush=True)
        run_script("generate_script.py", [
            args.article,
            "--output", podcast_script,
            "--turns", turns,
            "--model", cfg.get("ai_model", "anthropic/claude-sonnet-4-20250514"),
        ])
    with open(podcast_script, encoding="utf-8") as f:
        script_data = json.load(f)
    num_turns = len(script_data)
    total_chars = sum(len(s.get("text", "")) for s in script_data)
    host_count = sum(1 for s in script_data if s["role"] == "host")
    guest_count = sum(1 for s in script_data if s["role"] == "guest")
    print(f"📝 Phase 1 完成: {num_turns} 轮对话 (host:{host_count}, guest:{guest_count}), 约 {total_chars} 字", flush=True)

    # ------------------------------------------------------------------
    # Phase 2: Multi-speaker TTS
    # ------------------------------------------------------------------
    timing_path = os.path.join(workdir, "timing.json")
    audio_dir = os.path.join(workdir, "audio")
    if os.path.exists(timing_path):
        print(f"✅ Phase 2: Audio files already exist, skipping.", flush=True)
    else:
        print(f"🔊 Phase 2: Generating multi-speaker audio ({tts_backend})...", flush=True)
        run_script("generate_podcast_audio.py", [
            podcast_script,
            "--output-dir", audio_dir,
            "--timing-output", timing_path,
            "--host-voice", host_voice,
            "--guest-voice", guest_voice,
            "--rate", cfg.get("tts_rate", "-5%"),
            "--pitch", cfg.get("tts_pitch", "+0Hz"),
        ])
    with open(timing_path, encoding="utf-8") as f:
        timing_data = json.load(f)
    total_duration = sum(t["duration"] for t in timing_data)
    print(f"🔊 Phase 2 完成: 总时长 {total_duration/60:.0f} 分 {total_duration%60:.0f} 秒", flush=True)

    # ------------------------------------------------------------------
    # Phase 3: Assemble Podcast
    # ------------------------------------------------------------------
    if os.path.exists(final_podcast):
        print(f"✅ Phase 3: Podcast already exists, skipping.", flush=True)
    else:
        print("🎙️ Phase 3: Assembling podcast audio...", flush=True)
        assemble_args = [
            timing_path,
            "--output", final_podcast,
            "--gap-ms", gap_ms,
        ]
        if args.bgm:
            assemble_args.extend(["--bgm", args.bgm, "--bgm-volume", bgm_volume])
        if not args.no_normalize:
            assemble_args.extend(["--normalize", "--target-lufs", cfg.get("normalize_lufs", -16)])
        run_script("assemble_podcast.py", assemble_args)

    final_size_mb = os.path.getsize(final_podcast) / (1024 * 1024)
    print(f"🎙️ Phase 3 完成: {final_size_mb:.1f} MB", flush=True)

    # ------------------------------------------------------------------
    # Phase 4: Metadata Generation
    # ------------------------------------------------------------------
    if args.skip_metadata:
        print("⏭️ Phase 4: Skipped (--skip-metadata).", flush=True)
    elif os.path.exists(final_metadata):
        print(f"✅ Phase 4: Metadata already exists, skipping.", flush=True)
    else:
        print("📋 Phase 4: Generating metadata...", flush=True)
        meta_args = [
            podcast_script,
            "--timing", timing_path,
            "--output", final_metadata,
            "--gap-ms", gap_ms,
        ]
        if not args.article.startswith("http"):
            meta_args.extend(["--article", args.article])
        run_script("generate_metadata.py", meta_args)

    # Load metadata for summary
    metadata = {}
    if os.path.exists(final_metadata):
        with open(final_metadata, encoding="utf-8") as f:
            metadata = json.load(f)

    elapsed = time.time() - start_time
    podcast_duration = total_duration + len(timing_data) * gap_ms / 1000
    title = metadata.get("title", slug)

    print(f"""
╔══════════════════════════════════════════════════════════╗
║           🎙️ Article2Podcast 完成!                      ║
╠══════════════════════════════════════════════════════════╣
║  标题   : {title[:45]:<45s} ║
║  对话   : {f'{num_turns} 轮 (host:{host_count}, guest:{guest_count})':<45s} ║
║  时长   : {f'{podcast_duration/60:.0f} 分 {podcast_duration%60:.0f} 秒':<45s} ║
║  大小   : {f'{final_size_mb:.1f} MB':<45s} ║
║  耗时   : {f'{elapsed/60:.0f} 分 {elapsed%60:.0f} 秒':<45s} ║
║  音频   : {final_podcast[:45]:<45s} ║
║  元数据 : {final_metadata[:45]:<45s} ║
╚══════════════════════════════════════════════════════════╝
""", flush=True)


if __name__ == "__main__":
    main()
