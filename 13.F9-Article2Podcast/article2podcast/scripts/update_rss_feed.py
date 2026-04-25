#!/usr/bin/env python3
"""
RSS Feed 更新脚本：将新播客集添加到 RSS feed 并上传到 S3。

用法:
  # 添加单集
  python3 scripts/update_rss_feed.py --slug 2026-03-28-01-ai-bubble --feed /tmp/podcast-feed-full.xml

  # 批量添加（从 JSON 列表）
  python3 scripts/update_rss_feed.py --batch batch-slugs.json --feed /tmp/podcast-feed-full.xml

  # 添加并上传 S3 + 失效 CloudFront
  python3 scripts/update_rss_feed.py --slug 2026-03-28-01-ai-bubble --upload --invalidate

数据来源:
  - metadata.json: podcast 标题、描述、时长等
  - show-notes HTML: content:encoded 富文本
  - MP3 文件: 文件大小（enclosure length）

RSS item 结构（必须包含）:
  - <title>: metadata.title
  - <description><![CDATA[...]]>: metadata.description (完整节目简介，150-250字)
  - <content:encoded><![CDATA[...]]>: show-notes HTML (完整 Show Notes)
  - <enclosure url="..." length="..." type="audio/mpeg"/>
  - <guid isPermaLink="false">: slug
  - <pubDate>: RFC 2822 格式
  - <itunes:duration>: metadata.duration_formatted
  - <itunes:explicit>false</itunes:explicit>
  - <itunes:episodeType>full</itunes:episodeType>
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

# ── Config ──────────────────────────────────────────────────────────
S3_BUCKET = "claw2026"
S3_FEED_KEY = "podcast/feed.xml"
CF_DISTRIBUTION_ID = "E3KM4YV1GLQRGD"
CDN_BASE = "https://dwnvpa8lfeaci.cloudfront.net/podcast/episodes"
OUTPUT_DIR = os.path.expanduser("~/.openclaw/workspace/output")
DEFAULT_FEED = "/tmp/podcast-feed-full.xml"


def load_metadata(slug):
    """Load metadata.json for a podcast episode."""
    path = os.path.join(OUTPUT_DIR, f"{slug}-metadata.json")
    if not os.path.exists(path):
        print(f"  ⚠️  metadata not found: {path}", file=sys.stderr)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_show_notes_html(slug):
    """Load show-notes HTML (check /tmp first, then OUTPUT_DIR)."""
    for base in ["/tmp", OUTPUT_DIR]:
        path = os.path.join(base, f"{slug}-show-notes.html")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    # Try generating from markdown
    md_path = os.path.join(OUTPUT_DIR, f"{slug}-show-notes.md")
    if os.path.exists(md_path):
        try:
            sys.path.insert(0, "/home/ubuntu/.openclaw/skills/weixin-publisher")
            from md2weixin import md_to_weixin_html
            with open(md_path, encoding="utf-8") as f:
                md = f.read()
            html = md_to_weixin_html(md)
            # Cache it
            out = os.path.join("/tmp", f"{slug}-show-notes.html")
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)
            return html
        except Exception as e:
            print(f"  ⚠️  Failed to convert show-notes md→html: {e}", file=sys.stderr)
    return None


def get_mp3_size(slug):
    """Get MP3 file size in bytes."""
    path = os.path.join(OUTPUT_DIR, f"{slug}-podcast.mp3")
    if os.path.exists(path):
        return os.path.getsize(path)
    return 0


def build_item_xml(slug, meta, html, mp3_size, pub_date):
    """Build a single RSS <item> XML string."""
    title = meta.get("title", slug)
    description = meta.get("description", meta.get("subtitle", ""))
    duration = meta.get("duration_formatted", meta.get("total_duration", "00:00"))
    enclosure_url = f"{CDN_BASE}/{slug}.mp3"

    # Escape XML special chars in title (but not in CDATA)
    title_escaped = (title
                     .replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace('"', "&quot;"))

    lines = []
    lines.append("    <item>")
    lines.append(f"      <title>{title_escaped}</title>")
    lines.append(f"      <description><![CDATA[{description}]]></description>")
    if html:
        lines.append(f"      <content:encoded><![CDATA[{html}]]></content:encoded>")
    lines.append(f'      <enclosure url="{enclosure_url}" length="{mp3_size}" type="audio/mpeg"/>')
    lines.append(f'      <guid isPermaLink="false">{slug}</guid>')
    lines.append(f"      <pubDate>{pub_date}</pubDate>")
    lines.append(f"      <itunes:duration>{duration}</itunes:duration>")
    lines.append(f"      <itunes:explicit>false</itunes:explicit>")
    lines.append(f"      <itunes:episodeType>full</itunes:episodeType>")
    lines.append("    </item>")
    return "\n".join(lines)


def insert_items_into_feed(feed_path, items_xml_list):
    """Insert new items at the top of the channel (after channel metadata, before existing items)."""
    with open(feed_path, encoding="utf-8") as f:
        feed = f.read()

    # Find the first <item> or </channel> to insert before
    first_item = feed.find("<item>")
    if first_item == -1:
        # No existing items, insert before </channel>
        insert_pos = feed.find("</channel>")
    else:
        insert_pos = first_item

    new_content = "\n".join(items_xml_list) + "\n"
    feed = feed[:insert_pos] + new_content + feed[insert_pos:]

    # Atomic write
    tmp = feed_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(feed)
    os.rename(tmp, feed_path)
    return feed_path


def upload_to_s3(feed_path):
    """Upload feed to S3 with proper headers."""
    cmd = [
        "aws", "s3", "cp", feed_path,
        f"s3://{S3_BUCKET}/{S3_FEED_KEY}",
        "--content-type", "application/rss+xml; charset=utf-8",
        "--cache-control", "max-age=300,s-maxage=300",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ S3 upload failed: {result.stderr}", file=sys.stderr)
        return False
    print(f"  ✅ Uploaded to s3://{S3_BUCKET}/{S3_FEED_KEY}")
    return True


def invalidate_cloudfront():
    """Create CloudFront invalidation for feed.xml."""
    cmd = [
        "aws", "cloudfront", "create-invalidation",
        "--distribution-id", CF_DISTRIBUTION_ID,
        "--paths", f"/{S3_FEED_KEY}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  CloudFront invalidation failed (may lack permissions): {result.stderr.strip()[:100]}", file=sys.stderr)
        return False
    print(f"  ✅ CloudFront invalidation created")
    return True


def main():
    parser = argparse.ArgumentParser(description="Update podcast RSS feed with new episodes")
    parser.add_argument("--slug", help="Single episode slug to add")
    parser.add_argument("--batch", help="JSON file with list of slugs")
    parser.add_argument("--feed", default=DEFAULT_FEED, help=f"Feed XML path (default: {DEFAULT_FEED})")
    parser.add_argument("--pub-date", help="Publication date (YYYY-MM-DD), defaults to slug date")
    parser.add_argument("--upload", action="store_true", help="Upload to S3 after update")
    parser.add_argument("--invalidate", action="store_true", help="Invalidate CloudFront cache")
    parser.add_argument("--dry-run", action="store_true", help="Print items without modifying feed")
    args = parser.parse_args()

    if not args.slug and not args.batch:
        parser.error("Provide --slug or --batch")

    # Collect slugs
    if args.batch:
        with open(args.batch) as f:
            slugs = json.load(f)
    else:
        slugs = [args.slug]

    if not os.path.exists(args.feed):
        print(f"❌ Feed not found: {args.feed}", file=sys.stderr)
        sys.exit(1)

    # Check for duplicates
    with open(args.feed, encoding="utf-8") as f:
        existing = f.read()

    # Build items (newest first for insertion order)
    items_xml = []
    beijing_tz = timezone(timedelta(hours=8))

    for idx, slug in enumerate(slugs):
        if f">{slug}<" in existing:
            print(f"  ⏭️  {slug}: already in feed, skipping")
            continue

        meta = load_metadata(slug)
        if meta is None:
            print(f"  ❌ {slug}: no metadata, skipping")
            continue

        html = load_show_notes_html(slug)
        mp3_size = get_mp3_size(slug)

        # Determine pubDate
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", slug)
        if args.pub_date:
            base_date = datetime.strptime(args.pub_date, "%Y-%m-%d")
        elif date_match:
            base_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
        else:
            base_date = datetime.now()

        # Each episode gets a different hour (08:00 + idx)
        pub_dt = base_date.replace(hour=8 + idx, minute=0, second=0, tzinfo=beijing_tz)
        pub_date = pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z")

        item_xml = build_item_xml(slug, meta, html, mp3_size, pub_date)
        items_xml.append(item_xml)

        title = meta.get("title", slug)[:60]
        desc_len = len(meta.get("description", ""))
        html_len = len(html) if html else 0
        print(f"  ✅ {slug}")
        print(f"     title: {title}")
        print(f"     description: {desc_len} chars, content:encoded: {html_len} chars, mp3: {mp3_size} bytes")

    if not items_xml:
        print("\nNo new items to add.")
        return

    if args.dry_run:
        print("\n--- DRY RUN: would insert ---")
        print("\n".join(items_xml))
        return

    # Insert into feed (reverse so newest ends up first)
    items_xml.reverse()
    insert_items_into_feed(args.feed, list(reversed(items_xml)))
    print(f"\n✅ Added {len(items_xml)} episodes to {args.feed}")

    if args.upload:
        upload_to_s3(args.feed)

    if args.invalidate:
        invalidate_cloudfront()


if __name__ == "__main__":
    main()
