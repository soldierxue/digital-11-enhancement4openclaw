#!/usr/bin/env python3
"""
bili_uploader.py — B站上传封装
基于 bilitool 库，提供登录检查、视频上传、分P追加等功能
"""

import os
import sys
import subprocess


def check_bilitool_installed() -> bool:
    """检查 bilitool 是否已安装"""
    try:
        result = subprocess.run(
            ["bilitool", "--version"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_login_status() -> bool:
    """检查 B站登录状态"""
    try:
        result = subprocess.run(
            ["bilitool", "check"],
            capture_output=True, text=True, timeout=10
        )
        # bilitool check 成功返回 0
        return result.returncode == 0
    except Exception:
        return False


def upload_video_cli(
    video_path: str,
    title: str = "",
    desc: str = "",
    tags: str = "",
    tid: int = 232,
    cover: str = "",
    copyright: int = 1,
    source: str = "",
    cdn: str = "",
    yaml_path: str = "",
) -> dict:
    """
    通过 bilitool CLI 上传视频

    参数:
        video_path: 视频文件路径
        title: 视频标题
        desc: 视频描述
        tags: 逗号分隔的标签
        tid: 分区号（默认 232 科技杂谈）
        cover: 封面图路径
        copyright: 1=原创, 2=转载
        source: 转载来源（copyright=2 时必填）
        cdn: 上传线路（qn/bldsa/ws/bda2/tx，留空自动选择）
        yaml_path: YAML 配置文件路径

    返回: {"success": bool, "message": str, "bvid": str}
    """
    abs_path = os.path.abspath(video_path)
    if not os.path.isfile(abs_path):
        return {"success": False, "message": f"视频文件不存在: {abs_path}", "bvid": ""}

    cmd = ["bilitool", "upload", abs_path]

    if yaml_path and os.path.isfile(yaml_path):
        cmd.extend(["--yaml", yaml_path])
    else:
        if title:
            cmd.extend(["--title", title])
        if desc:
            cmd.extend(["--desc", desc])
        if tags:
            cmd.extend(["--tag", tags])
        if tid:
            cmd.extend(["--tid", str(tid)])
        if cover and os.path.isfile(cover):
            cmd.extend(["--cover", os.path.abspath(cover)])
        if copyright:
            cmd.extend(["--copyright", str(copyright)])
        if source:
            cmd.extend(["--source", source])
        if cdn:
            cmd.extend(["--cdn", cdn])

    print(f"  ▶ 执行: {' '.join(cmd[:4])}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=600  # 10 分钟超时
        )

        output = result.stdout + result.stderr
        print(output)

        if result.returncode == 0:
            # 尝试从输出中提取 BV 号
            bvid = ""
            for line in output.split('\n'):
                if 'BV' in line:
                    import re
                    match = re.search(r'(BV[a-zA-Z0-9]+)', line)
                    if match:
                        bvid = match.group(1)
                        break

            return {
                "success": True,
                "message": "上传成功",
                "bvid": bvid
            }
        else:
            return {
                "success": False,
                "message": f"上传失败: {output}",
                "bvid": ""
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "上传超时（10分钟）", "bvid": ""}
    except Exception as e:
        return {"success": False, "message": f"上传异常: {e}", "bvid": ""}


def upload_video_api(
    video_path: str,
    title: str = "",
    desc: str = "",
    tags: str = "",
    tid: int = 232,
    cover: str = "",
    copyright: int = 1,
    source: str = "",
    cdn: str = "",
    yaml_path: str = "",
) -> dict:
    """
    通过 bilitool Python API 上传视频（备选方案）

    与 CLI 方式功能一致，但直接调用 Python 接口，
    可以更好地捕获上传进度和错误信息。
    """
    try:
        from bilitool import UploadController
    except ImportError:
        return {
            "success": False,
            "message": "bilitool 未安装，请运行: pip install bilitool",
            "bvid": ""
        }

    try:
        controller = UploadController()
        controller.upload_video_entry(
            video_path=os.path.abspath(video_path),
            yaml=yaml_path or "",
            copyright=copyright,
            tid=tid,
            title=title,
            desc=desc,
            tag=tags,
            source=source,
            cover=os.path.abspath(cover) if cover and os.path.isfile(cover) else "",
            dynamic="",
            cdn=cdn,
        )
        return {"success": True, "message": "上传成功", "bvid": ""}
    except Exception as e:
        return {"success": False, "message": f"上传失败: {e}", "bvid": ""}


def append_video(video_path: str, bvid: str, cdn: str = "") -> dict:
    """
    追加视频到已有投稿（分P投稿）

    参数:
        video_path: 新分P视频文件路径
        bvid: 目标视频的 BV 号
        cdn: 上传线路
    """
    abs_path = os.path.abspath(video_path)
    if not os.path.isfile(abs_path):
        return {"success": False, "message": f"视频文件不存在: {abs_path}"}

    cmd = ["bilitool", "append", abs_path, "--bvid", bvid]
    if cdn:
        cmd.extend(["--cdn", cdn])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = result.stdout + result.stderr
        print(output)

        if result.returncode == 0:
            return {"success": True, "message": f"已追加到 {bvid}"}
        else:
            return {"success": False, "message": f"追加失败: {output}"}
    except Exception as e:
        return {"success": False, "message": f"追加异常: {e}"}
