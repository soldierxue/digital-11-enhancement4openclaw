#!/usr/bin/env python3
"""
video_cover.py — 智能视频封面截取
从视频中提取多个候选帧，通过 AI 评分选出最佳封面。

策略：
  1. 跳过片头片尾（通常是固定模板），聚焦正文段
  2. 在正文段中均匀采样 N 个候选帧
  3. 用 ffprobe 获取场景变化点（可选）
  4. 调用 Kiro CLI 对候选帧评分，选出信息密度最高、视觉最佳的一帧
  5. 裁剪/缩放到目标平台要求的比例

依赖：ffmpeg, ffprobe（已在 F6 流水线中安装）
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


# ── 视频信息 ──────────────────────────────────────────────

def get_video_info(video_path: str) -> dict:
    """获取视频时长和分辨率"""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries",
         "format=duration:stream=width,height,codec_type",
         "-of", "json", video_path],
        capture_output=True, text=True, timeout=10
    )
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    width, height = 0, 0
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            break
    return {"duration": duration, "width": width, "height": height}


# ── 候选帧提取 ────────────────────────────────────────────

def extract_candidate_frames(
    video_path: str,
    output_dir: str,
    count: int = 8,
    skip_head_pct: float = 0.10,
    skip_tail_pct: float = 0.08,
) -> list[str]:
    """
    从视频正文段均匀提取候选帧

    参数:
        video_path: 视频文件路径
        output_dir: 候选帧输出目录
        count: 候选帧数量（默认 8）
        skip_head_pct: 跳过片头比例（默认 10%）
        skip_tail_pct: 跳过片尾比例（默认 8%）

    返回: 候选帧文件路径列表
    """
    os.makedirs(output_dir, exist_ok=True)
    info = get_video_info(video_path)
    duration = info["duration"]

    # 计算采样区间（跳过片头片尾）
    start_time = duration * skip_head_pct
    end_time = duration * (1.0 - skip_tail_pct)
    span = end_time - start_time

    if span <= 0:
        # 视频太短，直接取中间帧
        start_time = duration * 0.3
        end_time = duration * 0.7
        span = end_time - start_time

    # 均匀采样时间点
    timestamps = []
    for i in range(count):
        t = start_time + span * (i + 0.5) / count
        timestamps.append(t)

    # ffmpeg 逐帧提取
    frame_paths = []
    for i, ts in enumerate(timestamps):
        output_path = os.path.join(output_dir, f"candidate_{i+1:02d}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", video_path,
             "-frames:v", "1", "-q:v", "2", output_path],
            capture_output=True, timeout=30
        )
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 1000:
            frame_paths.append(output_path)
        else:
            # 帧提取失败，跳过
            pass

    print(f"  ✓ 提取 {len(frame_paths)}/{count} 个候选帧")
    return frame_paths


# ── 场景变化检测（可选增强） ───────────────────────────────

def detect_scene_changes(
    video_path: str,
    output_dir: str,
    threshold: float = 0.3,
    max_frames: int = 12,
    skip_head_pct: float = 0.10,
    skip_tail_pct: float = 0.08,
) -> list[str]:
    """
    使用 ffmpeg scene 滤镜检测场景变化点，提取关键帧。
    场景变化点通常是视觉内容最丰富的时刻。

    如果检测失败或结果不足，回退到均匀采样。
    """
    info = get_video_info(video_path)
    duration = info["duration"]
    start_time = duration * skip_head_pct
    end_time = duration * (1.0 - skip_tail_pct)

    os.makedirs(output_dir, exist_ok=True)

    try:
        # 使用 select 滤镜检测场景变化
        result = subprocess.run(
            ["ffprobe", "-v", "quiet",
             "-show_entries", "frame=pts_time",
             "-select_streams", "v",
             "-of", "json",
             "-f", "lavfi",
             f"movie={video_path},select='gt(scene\\,{threshold})'"],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            frames = data.get("frames", [])
            # 过滤在正文区间内的场景变化点
            scene_times = []
            for f in frames:
                t = float(f.get("pts_time", 0))
                if start_time <= t <= end_time:
                    scene_times.append(t)

            if len(scene_times) >= 4:
                # 均匀采样 scene_times
                step = max(1, len(scene_times) // max_frames)
                selected = scene_times[::step][:max_frames]

                frame_paths = []
                for i, ts in enumerate(selected):
                    output_path = os.path.join(output_dir, f"scene_{i+1:02d}.jpg")
                    subprocess.run(
                        ["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", video_path,
                         "-frames:v", "1", "-q:v", "2", output_path],
                        capture_output=True, timeout=30
                    )
                    if os.path.isfile(output_path) and os.path.getsize(output_path) > 1000:
                        frame_paths.append(output_path)

                if frame_paths:
                    print(f"  ✓ 场景检测: {len(scene_times)} 个变化点，提取 {len(frame_paths)} 帧")
                    return frame_paths

    except Exception as e:
        print(f"  ⚠ 场景检测失败: {e}，回退到均匀采样")

    # 回退到均匀采样
    return extract_candidate_frames(video_path, output_dir)


# ── AI 评分选择最佳封面 ───────────────────────────────────

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def ai_select_best_frame(
    frame_paths: list[str],
    article_title: str = "",
) -> str:
    """
    调用 Kiro CLI 对候选帧评分，选出最佳封面。

    评分维度：
    - 信息密度（有数据卡片/图表/文字内容的帧优先）
    - 视觉吸引力（色彩丰富、构图清晰）
    - 避免纯黑/纯白/模糊帧

    如果 Kiro CLI 不可用，回退到启发式选择（中间帧）。
    """
    if not frame_paths:
        raise ValueError("没有候选帧可供选择")

    # 先用启发式过滤明显不好的帧（文件太小=纯色/黑屏）
    valid_frames = []
    for fp in frame_paths:
        size = os.path.getsize(fp)
        if size > 5000:  # >5KB 的帧才有内容
            valid_frames.append(fp)

    if not valid_frames:
        valid_frames = frame_paths

    # 如果只有 1-2 帧，直接返回
    if len(valid_frames) <= 2:
        return valid_frames[len(valid_frames) // 2]

    # 尝试 Kiro CLI 评分
    try:
        if not shutil.which("kiro-cli"):
            raise FileNotFoundError("kiro-cli not found")

        # 构建评分 prompt
        frame_list = "\n".join(
            f"  帧 {i+1}: {os.path.basename(fp)} ({os.path.getsize(fp)//1024}KB)"
            for i, fp in enumerate(valid_frames)
        )

        prompt = (
            f"我有 {len(valid_frames)} 个视频截图候选帧，需要选一个作为视频封面。\n"
            f"视频标题：{article_title or '科技知识分享'}\n\n"
            f"候选帧列表：\n{frame_list}\n\n"
            f"选择原则：\n"
            f"1. 优先选择有数据卡片、图表、结构化内容的帧（信息密度高）\n"
            f"2. 避免纯背景图、纯黑、纯白、模糊的帧\n"
            f"3. 优先选择中段帧（正文内容最丰富）\n"
            f"4. 文件越大通常内容越丰富\n\n"
            f"请只输出一个数字（1-{len(valid_frames)}），表示你选择的帧编号："
        )

        result = subprocess.run(
            ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools", prompt],
            capture_output=True, text=True, timeout=60
        )

        if result.returncode == 0:
            output = _ANSI_RE.sub('', result.stdout).strip()
            # 提取数字
            match = re.search(r'(\d+)', output)
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(valid_frames):
                    print(f"  🤖 AI 选择: 帧 {idx+1} ({os.path.basename(valid_frames[idx])})")
                    return valid_frames[idx]

    except Exception as e:
        print(f"  ⚠ AI 评分不可用: {e}")

    # 回退：启发式选择（文件最大的帧 = 内容最丰富）
    best = max(valid_frames, key=lambda fp: os.path.getsize(fp))
    print(f"  📊 启发式选择: {os.path.basename(best)} ({os.path.getsize(best)//1024}KB，文件最大)")
    return best


# ── 封面裁剪/缩放 ─────────────────────────────────────────

def crop_cover(
    input_path: str,
    output_path: str,
    target_ratio: str = "16:9",
    max_width: int = 1920,
) -> str:
    """
    裁剪/缩放封面到目标比例

    target_ratio:
        "16:9"  — B站推荐（1920×1080）
        "16:10" — B站封面（960×600）
        "3:2"   — 微信公众号封面
        "1:1"   — 视频号正方形封面
        "9:16"  — 竖屏视频封面
    """
    ratios = {
        "16:9": (16, 9),
        "16:10": (16, 10),
        "3:2": (3, 2),
        "1:1": (1, 1),
        "9:16": (9, 16),
    }

    if target_ratio not in ratios:
        # 直接复制
        shutil.copy2(input_path, output_path)
        return output_path

    rw, rh = ratios[target_ratio]

    # 使用 ffmpeg crop + scale
    # crop=计算居中裁剪区域，scale=缩放到目标宽度
    target_w = min(max_width, 1920)
    target_h = int(target_w * rh / rw)

    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path,
         "-vf", f"crop='min(iw,ih*{rw}/{rh})':'min(ih,iw*{rh}/{rw})',scale={target_w}:{target_h}",
         "-q:v", "2", output_path],
        capture_output=True, timeout=30
    )

    if os.path.isfile(output_path) and os.path.getsize(output_path) > 1000:
        print(f"  ✓ 封面已裁剪: {target_ratio} ({target_w}×{target_h})")
        return output_path

    # 裁剪失败，直接复制原图
    shutil.copy2(input_path, output_path)
    return output_path


# ── 主入口 ────────────────────────────────────────────────

def extract_smart_cover(
    video_path: str,
    output_path: str = None,
    target_ratio: str = "16:9",
    article_title: str = "",
    candidate_count: int = 8,
    use_scene_detection: bool = True,
) -> str:
    """
    智能封面提取完整流程

    参数:
        video_path: 视频文件路径
        output_path: 封面输出路径（默认: 视频同目录/cover.jpg）
        target_ratio: 目标比例（"16:9", "16:10", "1:1" 等）
        article_title: 文章标题（用于 AI 评分参考）
        candidate_count: 候选帧数量
        use_scene_detection: 是否使用场景变化检测

    返回: 封面文件路径
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    if not output_path:
        video_dir = os.path.dirname(os.path.abspath(video_path))
        output_path = os.path.join(video_dir, "cover.jpg")

    print(f"🖼️ 智能封面提取")
    print(f"  视频: {os.path.basename(video_path)}")
    print(f"  比例: {target_ratio}")

    info = get_video_info(video_path)
    print(f"  时长: {info['duration']:.0f}s, 分辨率: {info['width']}×{info['height']}")

    # 创建临时目录存放候选帧
    tmp_dir = tempfile.mkdtemp(prefix="video_cover_")

    try:
        # Step 1: 提取候选帧
        print("\n  ▶ Step 1: 提取候选帧")
        if use_scene_detection:
            frames = detect_scene_changes(video_path, tmp_dir, max_frames=candidate_count)
        else:
            frames = extract_candidate_frames(video_path, tmp_dir, count=candidate_count)

        if not frames:
            raise RuntimeError("未能提取任何候选帧")

        # Step 2: AI 选择最佳帧
        print("\n  ▶ Step 2: 选择最佳帧")
        best_frame = ai_select_best_frame(frames, article_title)

        # Step 3: 裁剪到目标比例
        print("\n  ▶ Step 3: 裁剪封面")
        crop_cover(best_frame, output_path, target_ratio)

        size_kb = os.path.getsize(output_path) / 1024
        print(f"\n  ✅ 封面已生成: {output_path} ({size_kb:.0f}KB)")
        return output_path

    finally:
        # 清理临时文件
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── CLI 入口 ──────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="智能视频封面截取")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--output", "-o", default=None, help="封面输出路径")
    parser.add_argument("--ratio", default="16:9",
                        choices=["16:9", "16:10", "3:2", "1:1", "9:16"],
                        help="目标比例（默认 16:9）")
    parser.add_argument("--title", default="", help="文章标题（辅助 AI 评分）")
    parser.add_argument("--candidates", type=int, default=8, help="候选帧数量")
    parser.add_argument("--no-scene-detect", action="store_true",
                        help="禁用场景变化检测，使用均匀采样")
    args = parser.parse_args()

    extract_smart_cover(
        video_path=args.video,
        output_path=args.output,
        target_ratio=args.ratio,
        article_title=args.title,
        candidate_count=args.candidates,
        use_scene_detection=not args.no_scene_detect,
    )


if __name__ == "__main__":
    main()
