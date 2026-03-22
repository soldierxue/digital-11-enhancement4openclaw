#!/usr/bin/env python3
"""
related_reading.py — 扩展阅读推荐
从 weixin-indexer 的文章索引中语义匹配 → 生成推荐 HTML 块

注意：文章索引同步逻辑已拆分到 F5-WexinArchiver/weixin-indexer，
本模块仅负责读取索引 + 语义推荐 + 生成 HTML。
"""

import os
import re
import json
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 索引路径：优先读取 weixin-indexer 的输出，回退到本地
INDEXER_PATH = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "9. F5-WexinArchiver", "weixin-indexer", "articles_index.json"
))
LOCAL_INDEX_PATH = os.path.join(SCRIPT_DIR, "articles_index.json")

# ANSI 转义序列正则（清理 Kiro CLI 输出）
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def load_articles_index() -> list:
    """
    加载文章索引（优先从 weixin-indexer 读取，回退到本地）
    """
    for path in [INDEXER_PATH, LOCAL_INDEX_PATH]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return []


def recommend_related(content_md: str, title: str,
                      articles_index: list, count: int = 5) -> list:
    """
    调用 Kiro CLI 语义匹配，从历史文章中推荐相关文章

    参数:
        content_md: 当前文章 Markdown 正文
        title: 当前文章标题
        articles_index: 已发布文章列表
        count: 推荐数量（默认 5）

    返回: [{"title": "...", "url": "...", "reason": "..."}]
    """
    if not articles_index:
        print("  ⚠ 文章索引为空，跳过扩展阅读推荐")
        return []

    # 排除当前文章自身
    candidates = [a for a in articles_index if a["title"] != title]
    if not candidates:
        print("  ⚠ 无候选文章，跳过扩展阅读推荐")
        return []

    # 构建候选列表文本（编号 + 标题 + 摘要）
    candidate_text = "\n".join(
        f"{i+1}. 《{a['title']}》— {a.get('digest', '')[:60]}"
        for i, a in enumerate(candidates)
    )

    # 截断正文避免 prompt 过长
    content_snippet = content_md[:2000] if len(content_md) > 2000 else content_md

    prompt = (
        f"你是一个文章推荐助手。根据当前文章内容，从候选列表中选出最相关的 {count} 篇文章。\n"
        f"当前文章标题：{title}\n"
        f"当前文章内容摘要：\n{content_snippet}\n\n"
        f"候选文章列表：\n{candidate_text}\n\n"
        f"请输出严格 JSON 数组，每个元素包含 index（候选编号，从1开始）和 reason（推荐理由，20字以内）。\n"
        f"只输出 JSON，不要输出任何其他内容。示例：\n"
        f'[{{"index": 1, "reason": "同为AI裁员话题"}}, {{"index": 3, "reason": "涉及法律监管"}}]'
    )

    try:
        result = subprocess.run(
            ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools", prompt],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            print(f"  ⚠ Kiro CLI 推荐失败: {result.stderr[:200]}")
            return _fallback_recommend(candidates, count)

        output = _ANSI_RE.sub('', result.stdout).strip()

        # 提取 JSON 数组
        json_match = re.search(r'\[.*\]', output, re.DOTALL)
        if not json_match:
            print(f"  ⚠ 无法解析推荐结果，使用回退策略")
            return _fallback_recommend(candidates, count)

        recommendations_raw = json.loads(json_match.group())

        # 映射回实际文章
        recommendations = []
        for rec in recommendations_raw[:count]:
            idx = rec.get("index", 0) - 1
            if 0 <= idx < len(candidates):
                recommendations.append({
                    "title": candidates[idx]["title"],
                    "url": candidates[idx]["url"],
                    "reason": rec.get("reason", ""),
                })

        if not recommendations:
            return _fallback_recommend(candidates, count)

        return recommendations

    except Exception as e:
        print(f"  ⚠ 语义匹配异常: {e}，使用回退策略")
        return _fallback_recommend(candidates, count)


def _fallback_recommend(candidates: list, count: int) -> list:
    """回退策略：按时间倒序取最近的文章"""
    sorted_articles = sorted(candidates, key=lambda a: a.get("date", ""), reverse=True)
    return [
        {"title": a["title"], "url": a["url"], "reason": "近期发布"}
        for a in sorted_articles[:count]
    ]


def build_related_reading_html(recommendations: list) -> str:
    """
    生成扩展阅读 HTML 块（带 inline style，直接插入微信 HTML）
    """
    if not recommendations:
        return ""

    items_html = ""
    for rec in recommendations:
        title = rec["title"]
        url = rec["url"]
        items_html += (
            f'<p style="margin: 8px 0; padding: 0; font-size: 15px; line-height: 1.75;">'
            f'📄 <a href="{url}" style="color: #0969da; text-decoration: none;">{title}</a>'
            f'</p>\n'
        )

    return (
        f'<section style="margin: 32px 0 24px 0; padding: 20px 16px; '
        f'background-color: #f6f8fa; border-radius: 8px; border-left: 4px solid #0969da;">\n'
        f'<p style="margin: 0 0 12px 0; padding: 0; font-size: 17px; '
        f'font-weight: 600; color: #1F2328; line-height: 1.5;">📚 扩展阅读</p>\n'
        f'{items_html}'
        f'</section>\n'
    )
