#!/usr/bin/env python3
"""
main.py — B站视频投稿入口
通过 bilitool 将视频上传到 Bilibili
"""

import os
import sys
import argparse

from bili_uploader import (
    check_bilitool_installed,
    check_login_status,
    upload_video_cli,
    append_video,
)
from video_cover import extract_smart_cover

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 常用分区映射
TID_MAP = {
    "科学科普": 201,
    "社科": 124,
    "人文历史": 228,
    "野生技术协会": 122,
    "软件应用": 230,
    "计算机技术": 231,
    "科技杂谈": 232,
    "数码": 95,
    "职业职场": 241,
    "日常": 21,
}


def load_article_content(article_path: str) -> str:
    """加载文章内容"""
    if not article_path or not os.path.isfile(article_path):
        return ""
    with open(article_path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(
        description="B站视频自动投稿（基于 bilitool）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 main.py /path/to/video.mp4 --article /path/to/article.md
  python3 main.py /path/to/video.mp4 --title "标题" --tags "AI,科技"
  python3 main.py /path/to/video.mp4 --tid 231 --cover cover.jpg
  python3 main.py /path/to/part2.mp4 --append BV1xx411x7xx

首次使用请先登录:
  bilitool login
        """
    )
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--article", default=None, help="原始文章路径（用于 AI 生成元数据）")
    parser.add_argument("--title", default=None, help="视频标题（≤80字）")
    parser.add_argument("--desc", default=None, help="视频描述")
    parser.add_argument("--tags", default=None, help="逗号分隔的标签")
    parser.add_argument("--tid", type=int, default=232, help="分区号（默认 232 科技杂谈）")
    parser.add_argument("--cover", default=None, help="封面图路径（留空则智能截取）")
    parser.add_argument("--no-auto-cover", action="store_true", help="禁用智能封面截取")
    parser.add_argument("--copyright", type=int, default=1, choices=[1, 2],
                        help="1=原创（默认）, 2=转载")
    parser.add_argument("--source", default="", help="转载来源 URL（copyright=2 时必填）")
    parser.add_argument("--cdn", default="", help="上传线路: qn/bldsa/ws/bda2/tx（留空自动）")
    parser.add_argument("--append", default=None, metavar="BVID",
                        help="追加到已有视频的 BV 号（分P投稿）")
    parser.add_argument("--yaml", default=None, help="YAML 配置文件路径")
    args = parser.parse_args()

    # ── 验证输入 ──
    if not os.path.isfile(args.video):
        print(f"✗ 视频文件不存在: {args.video}")
        sys.exit(1)

    size_mb = os.path.getsize(args.video) / (1024 * 1024)
    print(f"📺 B站视频投稿工具")
    print(f"━━━━━━━━━━━━━━━━━━━━")
    print(f"  视频: {args.video} ({size_mb:.1f} MB)")
    if args.article:
        print(f"  文章: {args.article}")
    print(f"  分区: tid={args.tid}")
    print(f"  版权: {'原创' if args.copyright == 1 else '转载'}")
    if args.append:
        print(f"  模式: 分P追加到 {args.append}")
    print()

    # ── Phase 1: 检查环境 ──
    print("▶ Phase 1: 检查环境")

    if not check_bilitool_installed():
        print("  ✗ bilitool 未安装")
        print("  请运行: pip install bilitool")
        sys.exit(1)
    print("  ✓ bilitool 已安装")

    if not check_login_status():
        print("  ✗ 未登录 B站")
        print("  请运行: bilitool login")
        sys.exit(1)
    print("  ✓ 已登录 B站")

    # ── 分P追加模式 ──
    if args.append:
        print(f"\n▶ 追加分P到 {args.append}")
        result = append_video(args.video, args.append, args.cdn)
        if result["success"]:
            print(f"\n✅ {result['message']}")
        else:
            print(f"\n✗ {result['message']}")
            sys.exit(1)
        return

    # ── Phase 2: 生成元数据 ──
    print("\n▶ Phase 2: 生成元数据")

    title = args.title
    desc = args.desc
    tags = args.tags
    content = ""

    if args.article:
        content = load_article_content(args.article)

    if not title and content:
        try:
            from metadata_generator import generate_title
            print("  🤖 AI 生成标题...")
            title = generate_title(content)
            print(f"  ✓ 标题: {title}")
        except Exception as e:
            print(f"  ⚠ AI 标题生成失败: {e}")

    if not desc and content:
        try:
            from metadata_generator import generate_description
            print("  🤖 AI 生成描述...")
            desc = generate_description(content)
            print(f"  ✓ 描述: {desc[:80]}...")
        except Exception as e:
            print(f"  ⚠ AI 描述生成失败: {e}")

    if not tags and content:
        try:
            from metadata_generator import generate_tags
            print("  🤖 AI 生成标签...")
            tags = generate_tags(content)
            print(f"  ✓ 标签: {tags}")
        except Exception as e:
            print(f"  ⚠ AI 标签生成失败: {e}")

    # 兜底默认值
    if not title:
        title = os.path.splitext(os.path.basename(args.video))[0]
        print(f"  ⚠ 使用文件名作为标题: {title}")
    if not tags:
        tags = "科技,AI"
        print(f"  ⚠ 使用默认标签: {tags}")

    # 智能封面截取：优先用户指定 → 智能截取 → B站自动截图
    cover_path = args.cover
    if not cover_path and not args.no_auto_cover:
        try:
            print("\n  🖼️ 智能封面截取...")
            cover_path = extract_smart_cover(
                video_path=args.video,
                output_path=os.path.join(SCRIPT_DIR, "auto_cover.jpg"),
                target_ratio="16:10",  # B站封面推荐 16:10
                article_title=title or "",
            )
        except Exception as e:
            print(f"  ⚠ 智能封面截取失败: {e}，将使用 B站自动截图")

    # ── Phase 3: 上传视频 ──
    print("\n▶ Phase 3: 上传视频")
    print(f"  📁 文件: {os.path.basename(args.video)} ({size_mb:.1f} MB)")
    print(f"  📝 标题: {title}")
    print(f"  🏷️ 标签: {tags}")
    print(f"  📂 分区: tid={args.tid}")

    result = upload_video_cli(
        video_path=args.video,
        title=title,
        desc=desc or "",
        tags=tags,
        tid=args.tid,
        cover=cover_path or "",
        copyright=args.copyright,
        source=args.source,
        cdn=args.cdn,
        yaml_path=args.yaml or "",
    )

    # ── 总结 ──
    print()
    print(f"📋 B站投稿总结")
    print(f"━━━━━━━━━━━━━━━━━━━━")
    print(f"  视频: {os.path.basename(args.video)} ({size_mb:.1f} MB)")
    print(f"  标题: {title}")
    if tags:
        print(f"  标签: {tags}")
    print(f"  分区: tid={args.tid}")
    print(f"  封面: {'自定义' if args.cover else ('智能截取' if cover_path else 'B站自动截图')}")
    print(f"  版权: {'原创' if args.copyright == 1 else '转载'}")

    if result["success"]:
        bvid = result.get("bvid", "")
        print(f"  状态: ✅ 投稿成功")
        if bvid:
            print(f"  BV号: {bvid}")
            print(f"  链接: https://www.bilibili.com/video/{bvid}")
        print(f"  ⏳ 视频将进入审核流程（通常 1-24 小时）")
    else:
        print(f"  状态: ✗ {result['message']}")

    print(f"━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
