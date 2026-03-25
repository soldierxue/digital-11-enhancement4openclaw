#!/usr/bin/env python3
"""
video_cover.py — 智能视频封面截取（与 F7 共享模块）
从视频中提取多个候选帧，通过 AI 评分选出最佳封面。

策略：
  1. 跳过片头片尾（通常是固定模板），聚焦正文段
  2. 在正文段中均匀采样 N 个候选帧
  3. 用 ffprobe 获取场景变化点（可选）
  4. 调用 Kiro CLI 对候选帧评分，选出信息密度最高、视觉最佳的一帧
  5. 裁剪/缩放到目标平台要求的比例

依赖：ffmpeg, ffprobe（已在 F6 流水线中安装）

注意：本文件与 F7-ChannelsPublisher/channels-publisher/video_cover.py 内容一致，
修改时请同步更新。后续可考虑提取为共享模块。
"""

# 导入路径：尝试从共享位置导入，回退到本地实现
import os
import sys

# 尝试导入 F7 的共享模块
_F7_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "11. F7-ChannelsPublisher", "channels-publisher"
))
if os.path.isdir(_F7_PATH) and _F7_PATH not in sys.path:
    sys.path.insert(0, _F7_PATH)

try:
    from video_cover import (  # noqa: F401
        get_video_info,
        extract_candidate_frames,
        detect_scene_changes,
        ai_select_best_frame,
        crop_cover,
        extract_smart_cover,
    )
except ImportError:
    # F7 不可用时的本地回退实现
    import json
    import re
    import shutil
    import subprocess
    import tempfile

    def get_video_info(video_path: str) -> dict:
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

    def extract_candidate_frames(video_path, output_dir, count=8,
                                  skip_head_pct=0.10, skip_tail_pct=0.08):
        os.makedirs(output_dir, exist_ok=True)
        info = get_video_info(video_path)
        duration = info["duration"]
        start = duration * skip_head_pct
        end = duration * (1.0 - skip_tail_pct)
        span = max(end - start, duration * 0.4)
        if span <= 0:
            start, span = duration * 0.3, duration * 0.4

        paths = []
        for i in range(count):
            t = start + span * (i + 0.5) / count
            out = os.path.join(output_dir, f"candidate_{i+1:02d}.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video_path,
                 "-frames:v", "1", "-q:v", "2", out],
                capture_output=True, timeout=30
            )
            if os.path.isfile(out) and os.path.getsize(out) > 1000:
                paths.append(out)
        return paths

    def detect_scene_changes(video_path, output_dir, threshold=0.3,
                              max_frames=12, skip_head_pct=0.10, skip_tail_pct=0.08):
        return extract_candidate_frames(video_path, output_dir, count=max_frames,
                                         skip_head_pct=skip_head_pct, skip_tail_pct=skip_tail_pct)

    def ai_select_best_frame(frame_paths, article_title=""):
        valid = [fp for fp in frame_paths if os.path.getsize(fp) > 5000] or frame_paths
        return max(valid, key=lambda fp: os.path.getsize(fp))

    def crop_cover(input_path, output_path, target_ratio="16:9", max_width=1920):
        ratios = {"16:9": (16,9), "16:10": (16,10), "3:2": (3,2), "1:1": (1,1), "9:16": (9,16)}
        if target_ratio not in ratios:
            shutil.copy2(input_path, output_path)
            return output_path
        rw, rh = ratios[target_ratio]
        tw = min(max_width, 1920)
        th = int(tw * rh / rw)
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path,
             "-vf", f"crop='min(iw,ih*{rw}/{rh})':'min(ih,iw*{rh}/{rw})',scale={tw}:{th}",
             "-q:v", "2", output_path],
            capture_output=True, timeout=30
        )
        if not (os.path.isfile(output_path) and os.path.getsize(output_path) > 1000):
            shutil.copy2(input_path, output_path)
        return output_path

    def extract_smart_cover(video_path, output_path=None, target_ratio="16:9",
                             article_title="", candidate_count=8, use_scene_detection=True):
        if not output_path:
            output_path = os.path.join(os.path.dirname(os.path.abspath(video_path)), "cover.jpg")
        tmp_dir = tempfile.mkdtemp(prefix="video_cover_")
        try:
            frames = extract_candidate_frames(video_path, tmp_dir, count=candidate_count)
            best = ai_select_best_frame(frames, article_title)
            crop_cover(best, output_path, target_ratio)
            return output_path
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="智能视频封面截取")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--ratio", default="16:9")
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    extract_smart_cover(args.video, args.output, args.ratio, args.title)
