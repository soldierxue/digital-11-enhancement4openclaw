#!/usr/bin/env python3
"""
metadata_generator.py — AI 生成视频号元数据（标题/描述/标签）
复用 Kiro CLI 调用模式（与 F4 cover_generator.py 一致）
"""

import re
import subprocess

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _call_kiro(prompt: str, timeout: int = 120) -> str:
    """调用 Kiro CLI，返回清理后的文本"""
    result = subprocess.run(
        ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools", prompt],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"Kiro CLI 失败: {result.stderr}")

    text = _ANSI_RE.sub('', result.stdout).strip()
    text = re.sub(r'^[>\s]+', '', text).strip()
    if not text:
        raise RuntimeError("Kiro CLI 返回空结果")
    return text


def generate_title(content: str, max_chars: int = 30) -> str:
    """生成视频号标题（≤30字）"""
    prompt = (
        f"请为以下文章生成一个适合微信视频号的标题，要求：\n"
        f"1. 不超过{max_chars}个中文字\n"
        f"2. 有吸引力，能引发好奇心\n"
        f"3. 适合短视频平台风格，简洁有力\n"
        f"只输出标题文本，不要输出任何其他内容：\n\n"
        + content[:3000]
    )
    title = _call_kiro(prompt)
    # 去除可能的引号包裹
    title = title.strip('"\'""''《》')
    if len(title) > max_chars:
        title = title[:max_chars]
    return title


def generate_description(content: str, max_chars: int = 1000) -> str:
    """生成视频号描述 + 话题标签"""
    prompt = (
        "请为以下文章生成微信视频号的描述文案，要求：\n"
        "1. 200字以内的描述正文\n"
        "2. 末尾另起一行，附加 3-5 个 #话题标签（如 #AI技术 #云计算）\n"
        "3. 风格：专业但不枯燥，适合科技内容创作者\n"
        "只输出描述文本，不要输出任何其他内容：\n\n"
        + content[:3000]
    )
    desc = _call_kiro(prompt)
    if len(desc) > max_chars:
        desc = desc[:max_chars]
    return desc


def generate_tags(content: str, count: int = 5) -> list[str]:
    """生成话题标签列表"""
    prompt = (
        f"请为以下文章生成 {count} 个微信视频号话题标签，要求：\n"
        f"1. 每个标签 2-6 个字\n"
        f"2. 与文章主题高度相关\n"
        f"3. 输出格式：每行一个标签，不带 # 号\n"
        f"只输出标签，不要输出任何其他内容：\n\n"
        + content[:2000]
    )
    text = _call_kiro(prompt)
    tags = [line.strip().lstrip('#').strip() for line in text.split('\n') if line.strip()]
    return tags[:count]
