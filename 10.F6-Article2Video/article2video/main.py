#!/usr/bin/env python3
"""Article2Video — Main pipeline entry point.

Converts a blog article (Markdown file or URL) into a narrated video with
Ken Burns effects, subtitles, and professional slide overlays.

Usage:
    python3 main.py <article_path_or_url> [options]

Options:
    --style photo|ai      Image source (default: photo)
    --slides N            Number of slides (default: 10)
    --voice VOICE_NAME    TTS voice (default: zh-CN-YunyangNeural)
    --skip-render         Stop after Phase 3 (useful for debugging)
    --skip-compress       Stop after Phase 4 (keep raw output)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import fcntl

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config():
    """Load config.json with path expansion."""
    cfg_path = os.path.join(SKILL_DIR, "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    # Expand ~ in paths
    for key in ("whisper_binary", "whisper_model", "output_dir"):
        if key in cfg:
            cfg[key] = os.path.expanduser(cfg[key])
    return cfg


def slugify(text: str) -> str:
    """Convert a title or URL into a filesystem-safe slug."""
    # Remove URL protocol and domain
    text = re.sub(r"https?://[^/]+/", "", text)
    # Remove file extension
    text = re.sub(r"\.\w+$", "", text)
    # Chinese-friendly: keep alphanumeric, CJK, hyphens
    text = re.sub(r"[^\w\u4e00-\u9fff-]", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:60] or "article"


def ensure_workdir(slug: str) -> str:
    """Create and return the working directory."""
    workdir = f"/tmp/article2video-{slug}"
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(os.path.join(workdir, "audio"), exist_ok=True)
    os.makedirs(os.path.join(workdir, "images"), exist_ok=True)
    return workdir


def run_script(script_name: str, args: list, cwd: str = None) -> subprocess.CompletedProcess:
    """Run a child script and stream output."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path] + [str(a) for a in args]
    print(f"\n{'='*60}")
    print(f"▶ Running: {script_name}")
    print(f"  Args: {' '.join(str(a) for a in args)}")
    print(f"{'='*60}\n", flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"\n❌ {script_name} failed with exit code {result.returncode}", flush=True)
        sys.exit(1)
    return result


def acquire_lock(workdir: str):
    """Prevent duplicate runs via PID file lock."""
    lock_path = os.path.join(workdir, ".pipeline.lock")
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("❌ Another pipeline instance is already running for this article.", flush=True)
        sys.exit(1)
    lock_fd.write(str(os.getpid()))
    lock_fd.flush()
    return lock_fd


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Article2Video pipeline")
    parser.add_argument("article", help="Path to Markdown file or URL")
    parser.add_argument("--style", choices=["photo", "ai"], default=None,
                        help="Image source: photo (Unsplash) or ai (Bedrock)")
    parser.add_argument("--slides", type=int, default=None,
                        help="Number of slides (default: from config)")
    parser.add_argument("--voice", default=None,
                        help="TTS voice name (default: from config)")
    parser.add_argument("--format", choices=["landscape", "portrait", "both"],
                        default=None,
                        help="Video format: landscape (16:9), portrait (9:16), both")
    parser.add_argument("--skip-render", action="store_true",
                        help="Stop after Phase 3")
    parser.add_argument("--skip-compress", action="store_true",
                        help="Stop after Phase 4")
    args = parser.parse_args()

    cfg = load_config()
    style = args.style or cfg.get("default_style", "photo")
    slides = args.slides or cfg.get("default_slides", 10)
    voice = args.voice or cfg.get("default_voice", "zh-CN-YunyangNeural")
    video_format = args.format or cfg.get("default_format", "landscape")

    # Determine slug and workdir
    slug = slugify(os.path.basename(args.article))
    workdir = ensure_workdir(slug)
    lock_fd = acquire_lock(workdir)

    output_dir = cfg.get("output_dir", os.path.expanduser("~/.openclaw/workspace/output"))
    os.makedirs(output_dir, exist_ok=True)

    # Determine output paths based on format
    if video_format == "portrait":
        final_output = os.path.join(output_dir, f"{slug}-video-portrait.mp4")
    elif video_format == "both":
        final_output = os.path.join(output_dir, f"{slug}-video.mp4")  # landscape
        final_output_portrait = os.path.join(output_dir, f"{slug}-video-portrait.mp4")
    else:
        final_output = os.path.join(output_dir, f"{slug}-video.mp4")

    start_time = time.time()
    print(f"""
╔══════════════════════════════════════════════════════════╗
║              Article2Video Pipeline                      ║
╠══════════════════════════════════════════════════════════╣
║  Article : {args.article[:45]:<45s} ║
║  Style   : {style:<45s} ║
║  Format  : {video_format:<45s} ║
║  Slides  : {str(slides):<45s} ║
║  Voice   : {voice:<45s} ║
║  Workdir : {workdir:<45s} ║
║  Output  : {final_output[:45]:<45s} ║
╚══════════════════════════════════════════════════════════╝
""", flush=True)

    # ------------------------------------------------------------------
    # Phase 1: Article → Speech Script
    # ------------------------------------------------------------------
    speech_script = os.path.join(workdir, "speech-script.json")
    if os.path.exists(speech_script):
        print(f"✅ Phase 1: speech-script.json already exists, skipping.", flush=True)
    else:
        print("📝 Phase 1: Generating speech script from article...", flush=True)
        run_script("split_article.py", [
            args.article,
            "--output", speech_script,
            "--slides", slides,
            "--model", cfg.get("ai_model", "anthropic/claude-sonnet-4-20250514"),
        ])
    with open(speech_script) as f:
        script_data = json.load(f)
    num_slides = len(script_data)
    total_chars = sum(len(s.get("speech", "")) for s in script_data)
    print(f"📝 Phase 1 完成: {num_slides} 段演讲稿, 约 {total_chars} 字", flush=True)

    # ------------------------------------------------------------------
    # Phase 2A: TTS Audio Generation
    # ------------------------------------------------------------------
    timing_path = os.path.join(workdir, "timing.json")
    full_audio_wav = os.path.join(workdir, "full-audio.wav")
    if os.path.exists(timing_path) and os.path.exists(full_audio_wav):
        print(f"✅ Phase 2A: Audio files already exist, skipping.", flush=True)
    else:
        print("🔊 Phase 2A: Generating TTS audio...", flush=True)
        run_script("generate_audio.py", [
            speech_script,
            "--output-dir", os.path.join(workdir, "audio"),
            "--timing-output", timing_path,
            "--voice", voice,
            f"--rate={cfg.get('tts_rate', '-5%')}",
            f"--pitch={cfg.get('tts_pitch', '+0Hz')}",
        ])
    with open(timing_path) as f:
        timing_data = json.load(f)
    total_duration = sum(t["duration"] for t in timing_data)
    print(f"🔊 Phase 2A 完成: 总时长 {total_duration/60:.0f} 分 {total_duration%60:.0f} 秒", flush=True)

    # ------------------------------------------------------------------
    # Phase 2B: Visual Assets
    # ------------------------------------------------------------------
    images_dir = os.path.join(workdir, "images")
    expected_images = [f"slide-{i+1:02d}.jpg" for i in range(num_slides)]
    existing_images = [f for f in expected_images if os.path.exists(os.path.join(images_dir, f))]
    # Also check for .png (AI images)
    if style == "ai":
        expected_images_png = [f"slide-{i+1:02d}.png" for i in range(num_slides)]
        existing_images = [f for f in expected_images_png if os.path.exists(os.path.join(images_dir, f))]

    if len(existing_images) >= num_slides:
        print(f"✅ Phase 2B: All {num_slides} images already exist, skipping.", flush=True)
    else:
        if style == "photo":
            print("🖼️ Phase 2B: Fetching photos from Unsplash...", flush=True)
            run_script("fetch_images.py", [
                speech_script,
                "--output-dir", images_dir,
                "--model", cfg.get("ai_model", "anthropic/claude-sonnet-4-20250514"),
            ])
        else:
            print("🎨 Phase 2B: Generating AI images via Bedrock...", flush=True)
            run_script("generate_ai_images.py", [
                speech_script,
                "--output-dir", images_dir,
                "--region", cfg.get("bedrock_region", "us-east-1"),
                "--model-id", cfg.get("bedrock_model_id", "amazon.nova-canvas-v1:0"),
                "--model", cfg.get("ai_model", "anthropic/claude-sonnet-4-20250514"),
            ])
    # Count actual images
    actual_count = len([f for f in os.listdir(images_dir)
                        if f.startswith("slide-") and (f.endswith(".jpg") or f.endswith(".png"))])
    print(f"🖼️ Phase 2B 完成: {actual_count}/{num_slides} 张图片就绪", flush=True)

    # ------------------------------------------------------------------
    # Phase 3: Subtitle Extraction
    # ------------------------------------------------------------------
    subtitles_path = os.path.join(workdir, "subtitles.json")
    if os.path.exists(subtitles_path):
        print(f"✅ Phase 3: Subtitles already exist, skipping.", flush=True)
    else:
        print("📄 Phase 3: Extracting subtitles with whisper.cpp...", flush=True)
        run_script("extract_subtitles.py", [
            full_audio_wav,
            "--output", subtitles_path,
            "--timing", timing_path,
            "--whisper-binary", cfg.get("whisper_binary", os.path.expanduser("~/whisper.cpp/main")),
            "--whisper-model", cfg.get("whisper_model", os.path.expanduser("~/whisper.cpp/models/ggml-small.bin")),
        ])
    with open(subtitles_path) as f:
        subs = json.load(f)
    print(f"📄 Phase 3 完成: {len(subs)} 条字幕", flush=True)

    if args.skip_render:
        print("\n⏭️ --skip-render specified, stopping after Phase 3.", flush=True)
        return

    # ------------------------------------------------------------------
    # Phase 4: Remotion Rendering
    # ------------------------------------------------------------------
    remotion_dir = os.path.join(SKILL_DIR, "remotion-template")

    # Determine which compositions to render
    render_jobs = []
    if video_format in ("landscape", "both"):
        render_jobs.append({
            "comp_id": cfg.get("remotion_composition_id", "AgentVideo"),
            "output": os.path.join(remotion_dir, "output.mp4"),
            "label": "landscape (16:9)",
            "final": final_output,
        })
    if video_format in ("portrait", "both"):
        render_jobs.append({
            "comp_id": "AgentVideoPortrait",
            "output": os.path.join(remotion_dir, "output-portrait.mp4"),
            "label": "portrait (9:16)",
            "final": final_output if video_format == "portrait" else final_output_portrait,
        })

    # Phase 4 prep: assemble data.json and copy assets (shared for all formats)
    data_json_path = os.path.join(remotion_dir, "public", "data.json")
    needs_prep = not os.path.exists(data_json_path)
    if not needs_prep:
        # Also re-prep if any render output is missing
        needs_prep = any(not os.path.exists(job["output"]) for job in render_jobs)

    if needs_prep:
        print("🎬 Phase 4: Preparing Remotion data...", flush=True)
        run_script("prepare_remotion.py", [
            "--workdir", workdir,
            "--remotion-dir", remotion_dir,
            "--timing", timing_path,
            "--subtitles", subtitles_path,
            "--speech-script", speech_script,
            "--style", style,
            "--fps", cfg.get("video_fps", 30),
            "--width", cfg.get("video_width", 1920),
            "--height", cfg.get("video_height", 1080),
            "--format", video_format,
        ])

    # Ensure node_modules exist
    node_modules = os.path.join(remotion_dir, "node_modules")
    if not os.path.exists(node_modules):
        print("📦 Installing Remotion dependencies (first time)...", flush=True)
        subprocess.run(["npm", "install"], cwd=remotion_dir, check=True)

    crf = cfg.get("video_crf", 23)
    raw_outputs = {}

    for job in render_jobs:
        if os.path.exists(job["output"]):
            print(f"✅ Phase 4: {job['label']} output already exists, skipping.", flush=True)
        else:
            print(f"🎬 Remotion 渲染开始 ({job['label']}, composition={job['comp_id']}, crf={crf})...", flush=True)
            print(f"   预计耗时: ~27 分钟 (ARM64)", flush=True)

            render_result = subprocess.run([
                "npx", "remotion", "render", job["comp_id"],
                "--output", job["output"],
                "--codec", "h264",
                "--crf", str(crf),
                "--timeout=600000",
                "--log=error",
            ], cwd=remotion_dir)
            if render_result.returncode != 0:
                print(f"❌ Remotion render failed for {job['label']}!", flush=True)
                sys.exit(1)

        raw_size_mb = os.path.getsize(job["output"]) / (1024 * 1024)
        raw_outputs[job["comp_id"]] = {"path": job["output"], "size_mb": raw_size_mb, "final": job["final"]}
        print(f"✅ Phase 4 ({job['label']}): 视频渲染完成, {raw_size_mb:.1f} MB", flush=True)

    if args.skip_compress:
        print(f"\n⏭️ --skip-compress specified, stopping after Phase 4.", flush=True)
        for k, v in raw_outputs.items():
            print(f"   {k}: {v['path']}", flush=True)
        return

    # ------------------------------------------------------------------
    # Phase 5: FFmpeg Compression
    # ------------------------------------------------------------------
    import shutil
    target_mb = cfg.get("compress_target_mb", 20)

    for comp_id, info in raw_outputs.items():
        final_path = info["final"]
        raw_path = info["path"]
        raw_mb = info["size_mb"]

        if os.path.exists(final_path):
            print(f"✅ Phase 5: {os.path.basename(final_path)} already exists, skipping.", flush=True)
            continue

        if raw_mb <= target_mb:
            print(f"📦 Phase 5: {comp_id} is already ≤{target_mb}MB, copying directly.", flush=True)
            shutil.copy2(raw_path, final_path)
        else:
            print(f"📦 Phase 5: Compressing {comp_id} {raw_mb:.0f}MB → ≤{target_mb}MB...", flush=True)
            run_script("compress_video.py", [
                raw_path,
                "--output", final_path,
                "--target-mb", target_mb,
                "--video-bitrate", cfg.get("compress_video_bitrate", "280k"),
                "--audio-bitrate", cfg.get("compress_audio_bitrate", "96k"),
            ])

    elapsed = time.time() - start_time
    print(f"""
╔══════════════════════════════════════════════════════════╗
║           ✅ Article2Video 完成!                         ║
╠══════════════════════════════════════════════════════════╣
║  格式   : {video_format:<45s} ║
║  幻灯片 : {str(num_slides) + ' 张':<45s} ║
║  时长   : {f'{total_duration/60:.0f} 分 {total_duration%60:.0f} 秒':<45s} ║
║  耗时   : {f'{elapsed/60:.0f} 分 {elapsed%60:.0f} 秒':<45s} ║""", flush=True)
    for comp_id, info in raw_outputs.items():
        final_size_mb = os.path.getsize(info["final"]) / (1024 * 1024) if os.path.exists(info["final"]) else 0
        print(f"║  {comp_id}: {info['size_mb']:.1f}MB → {final_size_mb:.1f}MB", flush=True)
        print(f"║    → {info['final']}", flush=True)
    print(f"""╚══════════════════════════════════════════════════════════╝
""", flush=True)


if __name__ == "__main__":
    main()
