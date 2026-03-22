#!/usr/bin/env python3
"""
main.py — 微信公众号文章发布入口
Phase 1: 快速出草稿（默认封面）
Phase 2: AI 封面生成 → 用户选择 → 更新草稿封面
"""

import os
import re
import sys
import json
import fcntl
import argparse
from datetime import date

from input_handler import load_article
from cover_generator import generate_covers, select_cover, generate_digest, check_kiro_cli
from md2weixin import md_to_weixin_html
from weixin_publish import WeixinPublisher
from related_reading import load_articles_index, recommend_related, build_related_reading_html


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DRAFT_DIR = os.path.join(SCRIPT_DIR, "草稿记录")
REGISTRY_PATH = os.path.join(DRAFT_DIR, "cover_registry.json")


def _load_registry() -> dict:
    """加载 registry（封面 + 草稿对应关系）"""
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_registry(registry: dict):
    """保存 registry"""
    os.makedirs(DRAFT_DIR, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def _ensure_article_entry(registry: dict, safe_title: str, article: dict, article_date: str) -> dict:
    """确保 registry 中有该文章的条目，返回条目引用"""
    if safe_title not in registry:
        registry[safe_title] = {
            "title": article["title"],
            "date": article_date,
            "covers": {},
            "content_images": {},
            "selected_style": None,
            "selected_media_id": None,
            "draft_media_id": None,
            "draft_created_at": None,
            "draft_updated_at": None,
        }
    # 兼容旧条目
    entry = registry[safe_title]
    if "content_images" not in entry:
        entry["content_images"] = {}
    return entry


def _upload_content_images(article: dict, publisher: WeixinPublisher,
                           entry: dict, source_dir: str) -> dict:
    """
    上传文中图片到微信 CDN，返回 image_map {原始路径: 微信URL}
    已上传过的从 registry 读取，跳过重复上传
    """
    images = article.get("images", [])
    if not images:
        return {}

    image_map = {}
    content_images = entry.setdefault("content_images", {})

    for img_ref in images:
        # 检查 registry 是否已有
        if img_ref in content_images and content_images[img_ref].get("weixin_url"):
            image_map[img_ref] = content_images[img_ref]["weixin_url"]
            print(f"  ✓ [已有] {img_ref} → {content_images[img_ref]['weixin_url'][:60]}...")
            continue

        # 解析图片实际路径
        if img_ref.startswith("http://") or img_ref.startswith("https://"):
            image_path = img_ref  # URL 直接传给 upload_content_image
        else:
            # 相对路径：先尝试相对于草稿记录目录，再尝试相对于脚本目录
            candidate = os.path.normpath(os.path.join(DRAFT_DIR, img_ref))
            if not os.path.isfile(candidate):
                candidate = os.path.normpath(os.path.join(source_dir, img_ref))
            if not os.path.isfile(candidate):
                candidate = os.path.normpath(os.path.join(SCRIPT_DIR, img_ref))
            if not os.path.isfile(candidate):
                print(f"  ✗ 图片不存在: {img_ref}")
                continue
            image_path = candidate

        try:
            print(f"  上传文中图片: {img_ref}...")
            weixin_url = publisher.upload_content_image(image_path)
            image_map[img_ref] = weixin_url
            content_images[img_ref] = {
                "local_path": image_path if not image_path.startswith("http") else "",
                "weixin_url": weixin_url,
                "uploaded_at": date.today().isoformat(),
            }
            print(f"  ✓ → {weixin_url[:80]}...")
        except Exception as e:
            print(f"  ✗ 上传失败 [{img_ref}]: {e}")

    return image_map


def publish_article(source: str, publish_mode: str = "draft"):
    """
    完整发布流程（两阶段）

    Phase 1: 快速出草稿（~10秒）— 使用默认封面
    Phase 2: AI 封面生成 → 用户选择 → 更新草稿封面（~2分钟）
    """
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    os.makedirs(DRAFT_DIR, exist_ok=True)
    registry = _load_registry()

    # ── 进程锁：防止并发执行创建重复草稿 ──
    lock_path = os.path.join(DRAFT_DIR, ".publish.lock")
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("\n⚠ 另一个发布进程正在运行，退出以避免重复草稿")
        lock_file.close()
        sys.exit(1)

    # ════════════════════════════════════════════════════════
    #  Phase 1: 快速出草稿
    # ════════════════════════════════════════════════════════

    # ── Step 1: 加载文章 ──
    print("\n=== Phase 1: 快速出草稿 ===")
    print("\n── Step 1: 加载文章 ──\n")
    article = load_article(source)
    print(f"  标题: {article['title']}")
    print(f"  字数: {article['word_count']}")
    print(f"  图片: {len(article['images'])} 张")
    if article["source_url"]:
        print(f"  来源: {article['source_url']}")

    article_date = article.get("date") or date.today().isoformat()
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', article["title"])
    entry = _ensure_article_entry(registry, safe_title, article, article_date)

    # ── Step 2: AI 生成引言 ──
    print("\n── Step 2: AI 生成引言 ──\n")
    try:
        if check_kiro_cli():
            ai_digest = generate_digest(article["content_md"])
            article["digest"] = ai_digest
            print(f"  ✓ AI 引言 ({len(ai_digest)} 字): {ai_digest}")
        else:
            print("  ⚠ Kiro CLI 不可用，使用默认摘要")
    except Exception as e:
        print(f"  ⚠ AI 引言生成失败: {e}，使用默认摘要")

    # ── Step 3: 保存草稿 Markdown ──
    print("\n── Step 3: 保存草稿 Markdown ──\n")
    draft_filename = f"[{article_date}]_[{safe_title}].md"
    draft_path = os.path.join(DRAFT_DIR, draft_filename)

    # 如果草稿已存在（可能被手动编辑过，如加入图片），优先读取已有草稿
    if os.path.exists(draft_path):
        with open(draft_path, "r", encoding="utf-8") as f:
            article["content_md"] = f.read()
        print(f"  ✓ 读取已有草稿: {draft_path}")
    else:
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(article["content_md"])
        print(f"  ✓ 已保存: {draft_path}")

    # 重新提取图片列表（草稿可能被手动编辑加入了图片）
    article["images"] = re.findall(r'!\[.*?\]\((.*?)\)', article["content_md"])

    # ── Step 3.5: 上传文中图片 ──
    publisher = WeixinPublisher(config_path)
    image_map = {}
    if article.get("images"):
        print("\n── Step 3.5: 上传文中图片 ──\n")
        publisher = WeixinPublisher(config_path)
        # source_dir: 输入源所在目录（用于解析相对路径图片）
        if os.path.isfile(source):
            source_dir = os.path.dirname(os.path.abspath(source))
        else:
            source_dir = SCRIPT_DIR
        image_map = _upload_content_images(article, publisher, entry, source_dir)
        _save_registry(registry)
        print(f"  ✓ 已上传 {len(image_map)}/{len(article['images'])} 张文中图片")

    # ── Step 4: Markdown → 微信 HTML ──
    print("\n── Step 4: Markdown → 微信 HTML ──\n")

    # ── Step 4.5: 扩展阅读推荐 ──
    related_html = ""
    related_count = config.get("related_reading_count", 5)
    try:
        print("\n── Step 4.5: 扩展阅读推荐 ──\n")
        # 从 weixin-indexer 读取文章索引（索引同步已拆分到 F5）
        articles_index = load_articles_index()

        if articles_index and check_kiro_cli():
            recommendations = recommend_related(
                article["content_md"], article["title"],
                articles_index, count=related_count
            )
            if recommendations:
                related_html = build_related_reading_html(recommendations)
                print(f"  ✓ 推荐 {len(recommendations)} 篇扩展阅读:")
                for r in recommendations:
                    print(f"    📄 {r['title']}")
            else:
                print("  ⚠ 未找到相关文章")
        else:
            if not articles_index:
                print("  ⚠ 无已发布文章，跳过扩展阅读")
            else:
                print("  ⚠ Kiro CLI 不可用，跳过语义匹配")
    except Exception as e:
        print(f"  ⚠ 扩展阅读推荐失败: {e}，跳过")

    html_content = md_to_weixin_html(
        article["content_md"],
        image_map=image_map or None,
        related_html=related_html or None,
    )
    print(f"  HTML 大小: {len(html_content)} 字符")
    if len(html_content) > 20000:
        print("  ⚠ 警告: HTML 超过 2 万字符，可能被微信截断")

    html_filename = f"[{article_date}]_[{safe_title}].html"
    html_path = os.path.join(DRAFT_DIR, html_filename)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✓ HTML 已保存: {html_path}")

    # ── Step 5: 上传默认封面 + 创建/更新草稿 ──
    print("\n── Step 5: 上传默认封面 + 创建/更新草稿 ──\n")
    default_cover = os.path.join(SCRIPT_DIR, config.get("default_cover", "assets/default_cover.jpg"))

    # 确定封面 media_id：优先用已选中的，否则用默认封面
    thumb_media_id = entry.get("selected_media_id")
    if thumb_media_id:
        print(f"  使用已选中的封面 media_id: {thumb_media_id}")
    else:
        # 检查默认封面是否已上传
        default_entry = entry.get("covers", {}).get("default")
        if default_entry and default_entry.get("media_id"):
            thumb_media_id = default_entry["media_id"]
            print(f"  使用已上传的默认封面 media_id: {thumb_media_id}")
        else:
            print("  上传默认封面...")
            thumb_media_id = publisher.upload_permanent_image(default_cover)
            print(f"  ✓ 默认封面 media_id: {thumb_media_id}")
            entry.setdefault("covers", {})["default"] = {
                "local_path": default_cover,
                "media_id": thumb_media_id,
                "uploaded_at": date.today().isoformat(),
            }

    # 构建草稿文章数据
    draft_article = {
        "title": article["title"],
        "author": article.get("author") or config.get("default_author", ""),
        "digest": article["digest"],
        "content": html_content,
        "content_source_url": article.get("source_url", ""),
        "thumb_media_id": thumb_media_id,
    }

    # 创建或更新草稿（Issue 2）
    # 重新加载 registry，防止并发进程已创建草稿（双重保险，配合文件锁）
    registry = _load_registry()
    entry = _ensure_article_entry(registry, safe_title, article, article_date)
    existing_draft_id = entry.get("draft_media_id")
    if existing_draft_id:
        print(f"  已有草稿 {existing_draft_id}，更新中...")
        try:
            publisher.update_draft(existing_draft_id, draft_article)
            print(f"  ✓ 草稿已更新: {existing_draft_id}")
            entry["draft_updated_at"] = date.today().isoformat()
        except Exception as e:
            print(f"  ⚠ 更新草稿失败: {e}，尝试新建...")
            existing_draft_id = None

    if not existing_draft_id:
        print("  创建新草稿...")
        draft_media_id = publisher.create_draft(draft_article)
        print(f"  ✓ 草稿 media_id: {draft_media_id}")
        entry["draft_media_id"] = draft_media_id
        entry["draft_created_at"] = date.today().isoformat()

    _save_registry(registry)

    print(f"\n  ✓ Phase 1 完成 — 草稿已就绪，可到微信后台预览")
    print(f"  草稿 ID: {entry['draft_media_id']}")

    # ════════════════════════════════════════════════════════
    #  Phase 2: AI 封面生成 → 用户选择 → 更新草稿
    # ════════════════════════════════════════════════════════
    print("\n=== Phase 2: AI 封面生成 + 更新草稿 ===")

    styles = config.get("cover_styles", ["cyberpunk", "scifi", "pixel", "comic", "ukiyoe"])
    region = config.get("bedrock_region", "us-west-2")

    # Issue 1: 检查是否已有封面，跳过生成
    existing_covers = entry.get("covers", {})
    ai_styles_done = [s for s in styles if s in existing_covers and existing_covers[s].get("media_id")]

    if len(ai_styles_done) == len(styles):
        print(f"\n  该文章已有 {len(ai_styles_done)} 张封面（已上传），跳过生成")
        covers = [
            {"style": s, "style_name": s, "path": existing_covers[s]["local_path"]}
            for s in ai_styles_done
        ]
    else:
        print(f"\n  已有 {len(ai_styles_done)}/{len(styles)} 张封面，生成剩余...")
        remaining_styles = [s for s in styles if s not in ai_styles_done]

        try:
            covers = generate_covers(
                article["content_md"], article["title"],
                styles=remaining_styles, region=region,
                output_dir=DRAFT_DIR, safe_title=safe_title
            )
        except Exception as e:
            print(f"\n  ⚠ 封面生成失败: {e}")
            covers = []

        # Issue 1: 上传所有新生成的封面并记录 media_id
        for c in covers:
            style = c["style"]
            if style in existing_covers and existing_covers[style].get("media_id"):
                continue  # 已上传过
            try:
                print(f"  上传 [{c.get('style_name', style)}] 封面...")
                mid = publisher.upload_permanent_image(c["path"])
                entry.setdefault("covers", {})[style] = {
                    "local_path": c["path"],
                    "media_id": mid,
                    "uploaded_at": date.today().isoformat(),
                }
                print(f"  ✓ media_id: {mid}")
            except Exception as e:
                print(f"  ✗ 上传失败 [{style}]: {e}")

        _save_registry(registry)

        # 合并已有 + 新生成的封面列表供选择
        all_covers = []
        for s in styles:
            cov = entry.get("covers", {}).get(s)
            if cov and cov.get("media_id"):
                all_covers.append({
                    "style": s,
                    "style_name": s,
                    "path": cov["local_path"],
                    "media_id": cov["media_id"],
                })
        covers = all_covers

    if covers:
        # 用户选择封面
        cover_path = select_cover(covers, default_cover=default_cover)

        # 找到选中封面的 media_id
        selected_style = None
        selected_media_id = None
        for c in covers:
            if c["path"] == cover_path:
                selected_style = c["style"]
                selected_media_id = c.get("media_id") or entry.get("covers", {}).get(c["style"], {}).get("media_id")
                break

        if selected_media_id and selected_media_id != thumb_media_id:
            # 更新草稿封面
            print(f"\n  更新草稿封面为 [{selected_style}]...")
            draft_article["thumb_media_id"] = selected_media_id
            try:
                publisher.update_draft(entry["draft_media_id"], draft_article)
                entry["selected_style"] = selected_style
                entry["selected_media_id"] = selected_media_id
                entry["draft_updated_at"] = date.today().isoformat()
                _save_registry(registry)
                print(f"  ✓ 草稿封面已更新")
            except Exception as e:
                print(f"  ✗ 更新草稿封面失败: {e}")
        elif selected_media_id:
            entry["selected_style"] = selected_style
            entry["selected_media_id"] = selected_media_id
            _save_registry(registry)
            print(f"  封面未变更，无需更新草稿")
    else:
        print("\n  无可用 AI 封面，保持默认封面")

    # ── 发布（可选）──
    if publish_mode in ("publish", "send"):
        print("\n=== 发布 ===\n")
        publish_id = publisher.publish(entry["draft_media_id"])
        print(f"  ✓ publish_id: {publish_id}")
        status = publisher.get_publish_status(publish_id)
        print(f"  发布状态: {status}")

    # ── 完成 ──
    fcntl.flock(lock_file, fcntl.LOCK_UN)
    lock_file.close()

    print("\n" + "=" * 50)
    print("✓ 完成")
    print(f"  模式: {publish_mode}")
    print(f"  标题: {article['title']}")
    print(f"  草稿 ID: {entry['draft_media_id']}")
    if publish_mode == "draft":
        print("  提示: 请到微信公众号后台查看草稿")
    print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="微信公众号文章自动发布工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从 URL 抓取并创建草稿
  python main.py https://example.com/article

  # 从本地 MD 文件创建草稿
  python main.py /path/to/article.md

  # 创建草稿并发布
  python main.py https://example.com/article --mode publish
        """
    )

    parser.add_argument("source", help="文章 URL 或本地 .md 文件路径")
    parser.add_argument(
        "--mode", choices=["draft", "publish", "send"],
        default="draft",
        help="发布模式: draft=仅草稿(默认), publish=发布, send=群发"
    )

    args = parser.parse_args()
    publish_article(args.source, args.mode)


if __name__ == "__main__":
    main()
