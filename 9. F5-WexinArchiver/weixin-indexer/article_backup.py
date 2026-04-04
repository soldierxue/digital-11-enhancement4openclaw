#!/usr/bin/env python3
"""
article_backup.py — 文章正文下载与 HTML 备份
遍历 articles_index.json，逐篇下载完整 HTML（保留图片和原始格式）
"""

import os
import re
import json
import time

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(SCRIPT_DIR, "articles_index.json")
ERRORS_PATH = os.path.join(SCRIPT_DIR, "backup_errors.json")
BACKUP_DIR_NAME = "历史备份"


def _fix_lazy_images(html: str) -> str:
    """将微信懒加载图片的 data-src 复制到 src，使本地浏览器能直接显示"""
    def _replace(m):
        tag = m.group(0)
        data_src = m.group(1)
        if re.search(r'(?<!data-)src="', tag):
            tag = re.sub(r'(?<!data-)src="[^"]*"', 'src="' + data_src + '"', tag, count=1)
        else:
            tag = tag.replace('<img ', '<img src="' + data_src + '" ', 1)
        return tag
    return re.sub(r'<img\b[^>]*?data-src="([^"]*)"[^>]*/?>', _replace, html)


def _safe_filename(title: str) -> str:
    """将标题转为安全文件名"""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', title)
    if len(name) > 100:
        name = name[:100]
    return name.strip()


def _load_errors() -> dict:
    if os.path.exists(ERRORS_PATH):
        with open(ERRORS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_errors(errors: dict):
    with open(ERRORS_PATH, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)


def backup_articles(articles: list, backup_dir: str = None,
                    delay: float = 2.5) -> dict:
    """
    批量下载文章完整 HTML

    参数:
        articles: 文章列表 [{"title", "url", "date", "digest"}]
        backup_dir: 备份根目录（默认 SCRIPT_DIR/历史备份）
        delay: 每篇间隔秒数

    返回: {"total", "success", "skipped", "failed", "repaired"}
    """
    if backup_dir is None:
        backup_dir = os.path.join(SCRIPT_DIR, BACKUP_DIR_NAME)

    errors = _load_errors()
    stats = {"total": len(articles), "success": 0, "skipped": 0, "failed": 0, "repaired": 0}

    for i, article in enumerate(articles):
        title = article.get("title", "")
        url = article.get("url", "")
        date_str = article.get("date", "unknown")

        if not title or not url:
            continue

        # 按年月归档
        month_dir = date_str[:7] if date_str and len(date_str) >= 7 else "unknown"
        target_dir = os.path.join(backup_dir, month_dir)
        safe_name = _safe_filename(title)
        target_path = os.path.join(target_dir, f"{date_str}_{safe_name}.html")

        # 增量：检查已备份文件
        if os.path.exists(target_path):
            # 检查是否有未修复的懒加载图片
            with open(target_path, "r", encoding="utf-8") as f:
                existing = f.read()
            # 找有 data-src 的 img，检查 src 是否为真实 URL
            has_broken = False
            for tag in re.findall(r'<img\b[^>]*data-src="https://[^"]*"[^>]*/?>',
                                  existing):
                src_m = re.search(r'(?<!data-)src="([^"]*)"', tag)
                if not src_m or not src_m.group(1).startswith("http"):
                    has_broken = True
                    break
            if not has_broken:
                stats["skipped"] += 1
                continue
            # 有问题，删掉重下
            os.remove(target_path)
            print(f"  [{i+1}/{len(articles)}] {title} (修复图片)...")
            is_repair = True
        else:
            print(f"  [{i+1}/{len(articles)}] {title}...")
            is_repair = False

        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            })
            resp.encoding = "utf-8"
            html = resp.text

            # 修复微信懒加载图片：data-src → src
            html = _fix_lazy_images(html)

            # 跳过空内容或错误页面
            if len(html) < 200:
                print(f"    ⚠ 内容过短 ({len(html)} 字符)，跳过")
                errors[url] = {"title": title, "error": f"内容过短: {len(html)} chars"}
                stats["failed"] += 1
                time.sleep(delay)
                continue

            os.makedirs(target_dir, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(html)

            stats["success"] += 1
            if is_repair:
                stats["repaired"] += 1
            errors.pop(url, None)

        except Exception as e:
            print(f"    ✗ 失败: {e}")
            errors[url] = {"title": title, "error": str(e)}
            stats["failed"] += 1

        # 限速
        if i < len(articles) - 1:
            time.sleep(delay)

        # 进度（每 20 篇）
        if (i + 1) % 20 == 0:
            print(f"  📥 进度: {i+1}/{len(articles)} "
                  f"(成功 {stats['success']}, 跳过 {stats['skipped']}, 失败 {stats['failed']})")

    _save_errors(errors)
    return stats
