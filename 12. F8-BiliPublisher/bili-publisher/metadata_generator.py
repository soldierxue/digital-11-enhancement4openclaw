#!/usr/bin/env python3
"""
metadata_generator.py — AI 生成 B站投稿元数据（标题/描述/标签）
复用 Kiro CLI 调用模式
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


def generate_title(content: str, max_chars: int = 80) -> str:
    """生成 B站视频标题（≤80字）"""
    prompt = (
        f"请为以下文章生成一个适合 B站（Bilibili）的视频标题，要求：\n"
        f"1. 不超过{max_chars}个字符\n"
        f"2. 有吸引力，适合科技/知识区风格\n"
        f"3. 可以用【】标注关键词，如【深度解析】\n"
        f"只输出标题文本，不要输出任何其他内容：\n\n"
        + content[:3000]
    )
    title = _call_kiro(prompt)
    title = title.strip('"\'""''《》')
    if len(title) > max_chars:
        title = title[:max_chars]
    return title


def generate_description(content: str, max_chars: int = 2000) -> str:
    """生成 B站视频描述"""
    prompt = (
        "请为以下文章生成 B站（Bilibili）视频描述，要求：\n"
        "1. 300字以内\n"
        "2. 第一行是一句话总结（吸引点击）\n"
        "3. 然后是 3-5 个要点（用 emoji 开头）\n"
        "4. 最后一行：更多内容请关注公众号「军见数科」\n"
        "只输出描述文本，不要输出任何其他内容：\n\n"
        + content[:3000]
    )
    desc = _call_kiro(prompt)
    if len(desc) > max_chars:
        desc = desc[:max_chars]
    return desc


def generate_tags(content: str, count: int = 8) -> str:
    """生成 B站标签（逗号分隔字符串）"""
    prompt = (
        f"请为以下文章生成 {count} 个 B站视频标签，要求：\n"
        f"1. 每个标签 2-8 个字\n"
        f"2. 与文章主题高度相关\n"
        f"3. 包含热门话题词（如 AI、科技、编程等）\n"
        f"4. 输出格式：用英文逗号分隔，如：AI,科技,编程\n"
        f"只输出标签，不要输出任何其他内容：\n\n"
        + content[:2000]
    )
    text = _call_kiro(prompt)
    # 清理：统一逗号，去除多余空格和 # 号
    tags = text.replace('，', ',').replace('#', '').strip()
    # 验证每个标签长度
    tag_list = [t.strip() for t in tags.split(',') if t.strip()]
    tag_list = [t[:20] for t in tag_list][:12]  # B站限制：每个≤20字，最多12个
    return ','.join(tag_list)
