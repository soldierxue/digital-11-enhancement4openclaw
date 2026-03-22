#!/usr/bin/env python3
"""
input_handler.py — 统一输入层
支持 URL 抓取和本地 .md 文件读取，统一输出 Markdown + 元数据 dict
"""

import os
import re
import yaml
import requests
from readability import Document
import html2text


def load_article(source: str) -> dict:
    """
    统一入口：自动识别输入类型并转为 Markdown + 元数据

    参数:
        source: URL 字符串 或 本地 .md 文件路径

    返回:
        {
            "title": str,
            "author": str,
            "date": str,
            "content_md": str,
            "digest": str,
            "source_url": str,
            "images": list,
            "word_count": int,
            "front_matter": dict
        }
    """
    source = source.strip()

    if source.startswith("http://") or source.startswith("https://"):
        return _fetch_from_url(source)
    elif os.path.isfile(source) and source.endswith(".md"):
        return _load_from_file(source)
    else:
        raise ValueError(
            f"无法识别输入类型: {source}\n"
            "支持: http(s):// URL 或 .md 文件路径"
        )


def _fetch_from_url(url: str) -> dict:
    """
    从 URL 抓取文章:
    1. requests 获取 HTML
    2. readability-lxml 提取正文
    3. html2text 转 Markdown
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    # readability 提取正文
    doc = Document(resp.text)
    title = doc.title()

    # 清理标题：去掉网站名后缀（如 " | Jason Xue"）
    title = title.strip()
    for sep in [" | ", " - ", " – ", " — "]:
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    content_html = doc.summary()

    # html2text 转 Markdown
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = False
    converter.body_width = 0  # 不自动换行
    content_md = converter.handle(content_html)

    # 提取图片
    images = re.findall(r'!\[.*?\]\((.*?)\)', content_md)

    # 生成摘要（纯文本前120字）
    plain_text = re.sub(r'[#*\[\]()!`>_\-\n]+', '', content_md).strip()
    digest = plain_text[:120]

    # 统计中文字数
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', content_md)
    word_count = len(chinese_chars) + len(content_md.split()) // 2

    return {
        "title": title.strip(),
        "author": "",
        "date": "",
        "content_md": content_md.strip(),
        "digest": digest,
        "source_url": url,
        "images": images,
        "word_count": word_count,
        "front_matter": {}
    }


def _load_from_file(filepath: str) -> dict:
    """
    从本地 .md 文件读取:
    1. 读取文件内容
    2. 解析 YAML front-matter
    3. 分离 front-matter 和正文
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    front_matter = {}
    content_md = raw

    # 解析 YAML front-matter
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', raw, re.DOTALL)
    if fm_match:
        try:
            front_matter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            front_matter = {}
        content_md = raw[fm_match.end():]

    title = front_matter.get("title", "")
    if not title:
        # 从正文第一个 # 标题提取
        h1 = re.search(r'^#\s+(.+)', content_md, re.MULTILINE)
        if h1:
            title = h1.group(1).strip()
        else:
            # 尝试从文件名格式 [date]_[title].md 提取标题
            basename = os.path.basename(filepath)
            title_match = re.match(r'\[.*?\]_\[(.+?)\]\.md$', basename)
            if title_match:
                title = title_match.group(1)
            else:
                title = os.path.splitext(basename)[0]

    author = front_matter.get("author", "")
    date = str(front_matter.get("date", ""))

    # 提取图片
    images = re.findall(r'!\[.*?\]\((.*?)\)', content_md)

    # 生成摘要
    plain_text = re.sub(r'[#*\[\]()!`>_\-\n]+', '', content_md).strip()
    digest = plain_text[:120]

    # 字数
    wc = front_matter.get("word_count", 0)
    if not wc:
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', content_md)
        wc = len(chinese_chars) + len(content_md.split()) // 2

    return {
        "title": title,
        "author": author,
        "date": date,
        "content_md": content_md.strip(),
        "digest": digest,
        "source_url": "",
        "images": images,
        "word_count": wc,
        "front_matter": front_matter
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("用法: python input_handler.py <URL 或 .md 文件路径>")
        sys.exit(1)

    result = load_article(sys.argv[1])
    print(json.dumps({
        "title": result["title"],
        "author": result["author"],
        "date": result["date"],
        "digest": result["digest"],
        "source_url": result["source_url"],
        "word_count": result["word_count"],
        "images_count": len(result["images"]),
        "content_preview": result["content_md"][:200] + "..."
    }, ensure_ascii=False, indent=2))
