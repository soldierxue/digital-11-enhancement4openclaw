#!/usr/bin/env python3
"""
cover_generator.py — AI 封面图生成
Kiro CLI 做文本智能（总结 + prompt 生成）→ Bedrock SD3.5 Large 出图
"""

import os
import re
import json
import shutil
import base64
import subprocess
import tempfile

import boto3

# 预定义风格
COVER_STYLES = {
    "cyberpunk": "赛博朋克",
    "scifi":     "科幻",
    "pixel":     "像素风",
    "comic":     "漫画风",
    "ukiyoe":    "浮世绘",
}

NEGATIVE_PROMPT = "text, words, letters, watermark, blurry, low quality, deformed"

# ANSI 转义序列正则（清理 Kiro CLI 输出中的终端颜色代码）
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def check_kiro_cli() -> bool:
    """检查 kiro-cli 是否可用"""
    kiro_path = shutil.which("kiro-cli")
    if not kiro_path:
        return False
    try:
        result = subprocess.run(
            ["kiro-cli", "--version"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def generate_summary(content_md: str) -> str:
    """
    调用 Kiro CLI 生成 300 字 Executive Summary
    """
    prompt = (
        "请阅读以下文章并用300字总结核心内容，只输出摘要文本，"
        "不要输出任何其他内容：\n\n" + content_md
    )

    result = subprocess.run(
        ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools", prompt],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"Kiro CLI 摘要生成失败: {result.stderr}")

    summary = _ANSI_RE.sub('', result.stdout).strip()
    if not summary:
        raise RuntimeError("Kiro CLI 返回空摘要")

    return summary


def generate_digest(content_md: str) -> str:
    """
    调用 Kiro CLI 生成 100 字以内的吸引读者的引言（用于微信 digest 字段）
    """
    prompt = (
        "请阅读以下文章，生成一段100字以内的中文引言，用于微信公众号文章摘要。"
        "要求：语言精炼有吸引力，能激发读者点击阅读全文的欲望。"
        "只输出引言文本，不要输出任何其他内容：\n\n" + content_md
    )

    result = subprocess.run(
        ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools", prompt],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"Kiro CLI 引言生成失败: {result.stderr}")

    digest = _ANSI_RE.sub('', result.stdout).strip()
    # 清理 Kiro CLI 可能输出的 markdown 引用符号
    digest = re.sub(r'^[>\s]+', '', digest).strip()
    if not digest:
        raise RuntimeError("Kiro CLI 返回空引言")

    # 确保不超过 120 字符（微信限制）
    if len(digest) > 120:
        digest = digest[:117] + "..."

    return digest


def generate_image_prompts(summary: str, styles: list = None) -> dict:
    """
    调用 Kiro CLI 基于摘要生成多风格的文生图 prompt
    返回: {"cyberpunk": "prompt text...", "scifi": "prompt text...", ...}
    """
    if styles is None:
        styles = list(COVER_STYLES.keys())

    style_desc = "、".join(COVER_STYLES[s] for s in styles if s in COVER_STYLES)

    prompt = (
        f"基于以下文章摘要，为每种视觉风格各生成一段英文文生图提示词。\n"
        f"要求：每段 prompt 适合 Stable Diffusion 模型，包含场景描述、"
        f"色彩氛围、构图要素，末尾加上 '3:2 aspect ratio, cover art, "
        f"high quality, detailed'。\n"
        f"风格列表：{style_desc}。\n"
        f"输出严格 JSON 格式，key 为英文风格名："
        f'{{"cyberpunk": "...", "scifi": "...", "pixel": "...", '
        f'"comic": "...", "ukiyoe": "..."}}\n'
        f"只输出 JSON，不要输出任何其他内容。\n\n"
        f"文章摘要：\n{summary}"
    )

    result = subprocess.run(
        ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools", prompt],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"Kiro CLI prompt 生成失败: {result.stderr}")

    output = _ANSI_RE.sub('', result.stdout).strip()

    # 用正则提取 JSON 块
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
    if not json_match:
        raise RuntimeError(f"无法从 Kiro CLI 输出中解析 JSON:\n{output[:500]}")

    try:
        prompts = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 解析失败: {e}\n原始输出:\n{output[:500]}")

    # 过滤只保留请求的风格
    return {k: v for k, v in prompts.items() if k in styles}


def generate_cover_images(prompts: dict, region: str = "us-west-2",
                          output_dir: str = None, safe_title: str = None) -> list:
    """
    调用 Bedrock SD3.5 Large 为每个 prompt 生成封面图
    返回候选封面列表

    参数:
        output_dir: 封面图保存目录（默认系统临时目录）
        safe_title: 文件名安全的文章标题，用于命名 [文章名]-[style].png
    """
    bedrock = boto3.client("bedrock-runtime", region_name=region)
    if output_dir:
        covers_dir = output_dir
    else:
        covers_dir = os.path.join(tempfile.gettempdir(), "weixin_covers")
    os.makedirs(covers_dir, exist_ok=True)

    covers = []

    for style, prompt_text in prompts.items():
        style_name = COVER_STYLES.get(style, style)
        if safe_title:
            output_path = os.path.join(covers_dir, f"{safe_title}-{style}.png")
        else:
            output_path = os.path.join(covers_dir, f"cover_{style}.png")

        print(f"  生成 [{style_name}] 封面图...")

        try:
            response = bedrock.invoke_model(
                modelId="stability.sd3-5-large-v1:0",
                body=json.dumps({
                    "prompt": prompt_text,
                    "negative_prompt": NEGATIVE_PROMPT,
                    "aspect_ratio": "3:2",
                    "output_format": "png"
                })
            )

            result = json.loads(response["body"].read())
            image_bytes = base64.b64decode(result["images"][0])

            with open(output_path, "wb") as f:
                f.write(image_bytes)

            covers.append({
                "style": style,
                "style_name": style_name,
                "path": output_path,
                "prompt": prompt_text
            })
            print(f"  ✓ [{style_name}] 已保存: {output_path}")

        except Exception as e:
            print(f"  ✗ [{style_name}] 生成失败: {e}")
            continue

    return covers


def select_cover(covers: list, default_cover: str = "assets/default_cover.jpg") -> str:
    """
    交互式让用户选择封面图
    输入 0 = 使用默认封面
    返回选中图片的路径
    """
    if not covers:
        print("  没有可用的 AI 封面图，使用默认封面")
        return default_cover

    print("\n封面图候选（请选择编号）:\n")
    for i, c in enumerate(covers, 1):
        print(f"  [{i}] {c['style_name']}  → {c['path']}")
    print(f"  [0] 使用默认封面")

    while True:
        try:
            choice = input("\n请输入编号: ").strip()
            idx = int(choice)
            if idx == 0:
                return default_cover
            if 1 <= idx <= len(covers):
                selected = covers[idx - 1]
                print(f"\n  ✓ 已选择: [{selected['style_name']}]")
                return selected["path"]
            print(f"  请输入 0~{len(covers)} 之间的数字")
        except (ValueError, EOFError):
            print(f"  请输入 0~{len(covers)} 之间的数字")


def generate_covers(content_md: str, title: str,
                    styles: list = None,
                    region: str = "us-west-2",
                    output_dir: str = None,
                    safe_title: str = None) -> list:
    """
    完整封面生成流程（入口函数）

    参数:
        output_dir: 封面图保存目录（默认系统临时目录）
        safe_title: 文件名安全的文章标题，用于命名 [文章名]-[style].png
    """
    print("\n=== AI 封面图生成 ===\n")

    # Step 1: 检查 Kiro CLI
    print("检查 Kiro CLI...")
    if not check_kiro_cli():
        raise RuntimeError(
            "Kiro CLI 不可用，请确认已安装并登录:\n"
            "  which kiro-cli\n"
            "  kiro-cli whoami"
        )
    print("  ✓ Kiro CLI 可用\n")

    # Step 2: 生成摘要
    print("生成 Executive Summary...")
    summary = generate_summary(content_md)
    print(f"  ✓ 摘要已生成 ({len(summary)} 字)\n")

    # Step 3: 生成图片 prompt
    print("生成文生图提示词...")
    prompts = generate_image_prompts(summary, styles)
    print(f"  ✓ 已生成 {len(prompts)} 种风格的 prompt\n")

    # Step 4: Bedrock 出图
    print("调用 Bedrock SD3.5 Large 生成封面图...")
    covers = generate_cover_images(prompts, region,
                                   output_dir=output_dir,
                                   safe_title=safe_title)
    print(f"\n  ✓ 成功生成 {len(covers)} 张封面图\n")

    return covers


if __name__ == "__main__":
    print("cover_generator.py — 独立测试")
    print(f"Kiro CLI 可用: {check_kiro_cli()}")
