#!/usr/bin/env python3
"""
sync_articles.py — 微信公众号文章索引同步 + 内容备份

用法:
  python sync_articles.py                  # 同步索引（三来源合并）
  python sync_articles.py --setup-admin    # 交互式设置后台 session
  python sync_articles.py --auto-session   # CDP 自动提取后台 session + 同步索引
  python sync_articles.py --backup         # 同步索引 + 下载正文备份
  python sync_articles.py --backup-only    # 仅下载正文备份（使用已有索引）
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(SCRIPT_DIR, "articles_index.json")
ADMIN_SESSION_PATH = os.path.join(SCRIPT_DIR, "weixin_admin_session.json")


# ── 索引同步 ──────────────────────────────────────────────


def _timestamp_to_date(ts: int) -> str:
    """Unix 时间戳 → YYYY-MM-DD"""
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _load_admin_session() -> dict:
    """加载微信后台管理 session"""
    if not os.path.exists(ADMIN_SESSION_PATH):
        return {}
    with open(ADMIN_SESSION_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _fetch_material_articles(client) -> list:
    """来源 1: material/batchget_material (type=news) — 旧体系"""
    articles = []
    offset = 0
    while True:
        data = client.get_published_articles(offset=offset, count=20)
        items = data.get("item", [])
        if not items:
            break
        for item in items:
            content = item.get("content", {})
            news_items = content.get("news_item", [])
            update_time = item.get("update_time", 0)
            for news in news_items:
                entry = {
                    "title": news.get("title", ""),
                    "url": news.get("url", ""),
                    "digest": news.get("digest", ""),
                    "date": _timestamp_to_date(update_time),
                    "source": "material",
                }
                if entry["title"] and entry["url"]:
                    articles.append(entry)
        total = data.get("total_count", 0)
        offset += len(items)
        if offset >= total:
            break
    return articles


def _fetch_admin_articles(client) -> list:
    """来源 3: 后台管理接口 appmsg?action=list_ex — 全量"""
    session = _load_admin_session()
    cookie = session.get("cookie", "")
    token = session.get("token", "")
    fakeid = session.get("fakeid", "")

    if not cookie or not token:
        print("    ⚠ weixin_admin_session.json 缺少 cookie/token，跳过后台接口")
        return []

    articles = []
    begin = 0
    page_size = 5
    total = None

    while True:
        try:
            data = client.get_admin_articles(
                cookie=cookie, token=token, fakeid=fakeid,
                begin=begin, count=page_size
            )
        except RuntimeError as e:
            print(f"    ⚠ 后台接口失败 (begin={begin}): {e}")
            break

        msg_list = data.get("app_msg_list", [])
        if not msg_list:
            break

        if total is None:
            total = int(data.get("app_msg_cnt", 0))
            print(f"    总文章数: {total}")

        for item in msg_list:
            create_time = item.get("create_time", 0)
            entry = {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "digest": item.get("digest", ""),
                "date": _timestamp_to_date(create_time),
                "source": "admin",
            }
            if entry["title"] and entry["url"]:
                articles.append(entry)

        begin += len(msg_list)
        if total and begin >= total:
            break

        if begin % 50 == 0 or begin >= (total or 0):
            print(f"    进度: {begin}/{total} 篇...")

        time.sleep(1)

    return articles


def _fetch_freepublish_articles(client) -> list:
    """来源 2: freepublish/batchget — 新体系（订阅号通常无权限）"""
    articles = []
    offset = 0
    while True:
        try:
            data = client.get_freepublish_articles(offset=offset, count=20)
        except RuntimeError as e:
            print(f"  ⚠ freepublish/batchget 失败: {e}")
            break
        items = data.get("item", [])
        if not items:
            break
        for item in items:
            content = item.get("content", {})
            news_items = content.get("news_item", [])
            update_time = item.get("update_time", 0)
            for news in news_items:
                entry = {
                    "title": news.get("title", ""),
                    "url": news.get("url", ""),
                    "digest": news.get("digest", ""),
                    "date": _timestamp_to_date(update_time),
                    "source": "freepublish",
                }
                if entry["title"] and entry["url"]:
                    articles.append(entry)
        total = data.get("total_count", 0)
        offset += len(items)
        if offset >= total:
            break
    return articles


def sync_published_articles(client) -> list:
    """
    三来源合并去重，保存到 articles_index.json
    以 URL 为主键，admin > freepublish > material
    返回: [{"title", "url", "date", "digest"}]
    """
    print("  同步已发布文章索引...")

    admin_session = _load_admin_session()
    has_admin = bool(admin_session.get("cookie") and admin_session.get("token"))

    # 来源 1
    print("    [1/3] material/batchget_material (type=news)...")
    material_articles = _fetch_material_articles(client)
    print(f"    ✓ 旧体系图文素材: {len(material_articles)} 篇")

    # 来源 2
    print("    [2/3] freepublish/batchget...")
    freepublish_articles = _fetch_freepublish_articles(client)
    print(f"    ✓ 新体系已发布文章: {len(freepublish_articles)} 篇")

    # 来源 3
    admin_articles = []
    if has_admin:
        print("    [3/3] 后台管理接口 appmsg?action=list_ex...")
        admin_articles = _fetch_admin_articles(client)
        print(f"    ✓ 后台管理接口: {len(admin_articles)} 篇")
    else:
        print("    [3/3] 后台管理接口: 跳过（无 weixin_admin_session.json）")

    # 合并去重
    seen_urls = {}
    for a in material_articles:
        seen_urls[a["url"]] = a
    for a in freepublish_articles:
        seen_urls[a["url"]] = a
    for a in admin_articles:
        seen_urls[a["url"]] = a

    all_articles = list(seen_urls.values())
    all_articles.sort(key=lambda a: a.get("date", ""), reverse=True)

    # 移除 source 字段
    for a in all_articles:
        a.pop("source", None)

    # 保存索引
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"  ✓ 合并去重后共 {len(all_articles)} 篇已发布文章")
    return all_articles


def load_articles_index() -> list:
    """加载本地文章索引"""
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ── 交互式设置 ────────────────────────────────────────────


def setup_admin_session():
    """交互式设置微信后台管理 session"""
    print("\n=== 设置微信后台管理 Session ===\n")
    print("请按以下步骤获取所需信息：")
    print("  1. 用浏览器登录 https://mp.weixin.qq.com")
    print("  2. 打开开发者工具（F12）→ Network 选项卡")
    print("  3. 在后台左侧菜单点击「内容与互动」→「图文消息」")
    print("  4. 在 Network 中找到 appmsg?action=list_ex 请求")
    print("  5. 从请求头中复制 Cookie")
    print("  6. 从请求 URL 参数中复制 token\n")

    cookie = input("Cookie（整行粘贴）: ").strip()
    token = input("Token: ").strip()

    if not cookie or not token:
        print("\n✗ cookie/token 不能为空")
        sys.exit(1)

    session = {
        "cookie": cookie,
        "token": token,
        "note": "从微信公众号后台获取，cookie 有效期约 2 小时，过期需重新获取",
    }

    with open(ADMIN_SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 已保存到 {ADMIN_SESSION_PATH}")
    print("  现在可以运行 python sync_articles.py 同步全部文章\n")


# ── 主入口 ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="微信公众号文章索引同步 + 内容备份",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python sync_articles.py                  # 同步索引
  python sync_articles.py --setup-admin    # 手动设置后台 session
  python sync_articles.py --auto-session   # CDP 自动提取 session + 同步索引
  python sync_articles.py --auto-session --backup  # 自动提取 + 同步 + 备份
  python sync_articles.py --backup         # 同步索引 + 下载正文备份
  python sync_articles.py --backup-only    # 仅下载正文备份
        """
    )
    parser.add_argument("--setup-admin", action="store_true",
                        help="交互式设置微信后台 session（cookie + token）")
    parser.add_argument("--auto-session", action="store_true",
                        help="通过 CDP 自动提取微信后台 session（需浏览器已登录）")
    parser.add_argument("--cdp-url",
                        default=os.environ.get("CDP_URL", "http://127.0.0.1:9222"),
                        help="CDP 地址，配合 --auto-session 使用 (默认: http://127.0.0.1:9222)")
    parser.add_argument("--backup", action="store_true",
                        help="同步索引后下载文章正文备份")
    parser.add_argument("--backup-only", action="store_true",
                        help="仅下载正文备份（使用已有索引）")
    args = parser.parse_args()

    if args.setup_admin:
        setup_admin_session()
        return

    # CDP 自动提取 session
    if args.auto_session:
        from auto_session import auto_extract_session
        result = auto_extract_session(cdp_url=args.cdp_url)
        if not result:
            print("✗ 自动提取 session 失败，可改用 --setup-admin 手动设置")
            sys.exit(1)
        print()  # 空行分隔

    # 仅备份模式
    if args.backup_only:
        articles = load_articles_index()
        if not articles:
            print("✗ 无本地索引，请先运行 python sync_articles.py 同步")
            sys.exit(1)
        print(f"\n使用已有索引: {len(articles)} 篇文章")
        from article_backup import backup_articles
        stats = backup_articles(articles)
        print(f"\n✓ 备份完成: 成功 {stats['success']}, "
              f"跳过 {stats['skipped']}, 失败 {stats['failed']}")
        return

    # 同步索引
    from weixin_client import WeixinClient
    client = WeixinClient()
    articles = sync_published_articles(client)

    print(f"\n共同步 {len(articles)} 篇已发布文章到 articles_index.json")
    if articles:
        dates = [a.get("date", "") for a in articles if a.get("date")]
        if dates:
            print(f"  日期范围: {min(dates)} ~ {max(dates)}")

    for i, a in enumerate(articles[:10], 1):
        print(f"  {i}. [{a.get('date', '')}] {a['title']}")
    if len(articles) > 10:
        print(f"  ... 共 {len(articles)} 篇")

    # 同步 + 备份模式
    if args.backup:
        print("\n=== 下载文章正文备份 ===\n")
        from article_backup import backup_articles
        stats = backup_articles(articles)
        print(f"\n✓ 备份完成: 成功 {stats['success']}, "
              f"跳过 {stats['skipped']}, 失败 {stats['failed']}")


if __name__ == "__main__":
    main()
