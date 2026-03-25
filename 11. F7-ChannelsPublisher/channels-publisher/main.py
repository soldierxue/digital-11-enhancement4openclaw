#!/usr/bin/env python3
"""
main.py — 微信视频号发布入口
通过 CDP 浏览器自动化将视频发布到视频号创作者中心
"""

import os
import sys
import argparse

from cdp_client import find_channels_tab, navigate_to_channels, connect_tab
from channels_uploader import ChannelsUploader
from video_cover import extract_smart_cover


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_article_content(article_path: str) -> str:
    """加载文章内容（用于 AI 生成元数据）"""
    if not article_path or not os.path.isfile(article_path):
        return ""
    with open(article_path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(
        description="微信视频号自动发布（CDP 浏览器自动化）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 main.py /path/to/video.mp4
  python3 main.py /path/to/video.mp4 --article /path/to/article.md
  python3 main.py /path/to/video.mp4 --title "我的视频" --desc "视频描述"
  python3 main.py /path/to/video.mp4 --cover /path/to/cover.jpg --publish

前置条件:
  1. Chrome 已启用 Remote Debugging (--remote-debugging-port=9222)
  2. 已在浏览器中登录 channels.weixin.qq.com
        """
    )
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--article", default=None, help="原始文章路径（用于 AI 生成标题/描述）")
    parser.add_argument("--cover", default=None, help="自定义封面图路径（留空则智能截取）")
    parser.add_argument("--no-auto-cover", action="store_true", help="禁用智能封面截取")
    parser.add_argument("--title", default=None, help="手动指定标题（跳过 AI 生成）")
    parser.add_argument("--desc", default=None, help="手动指定描述（跳过 AI 生成）")
    parser.add_argument("--cdp-url", default=os.environ.get("CDP_URL", "http://127.0.0.1:9222"),
                        help="CDP 地址 (默认: http://127.0.0.1:9222)")
    parser.add_argument("--publish", action="store_true", help="直接发布（默认仅保存草稿）")
    args = parser.parse_args()

    # ── 验证输入 ──
    if not os.path.isfile(args.video):
        print(f"✗ 视频文件不存在: {args.video}")
        sys.exit(1)

    size_mb = os.path.getsize(args.video) / (1024 * 1024)
    print(f"📹 视频号发布工具")
    print(f"━━━━━━━━━━━━━━━━━━━━")
    print(f"  视频: {args.video} ({size_mb:.1f} MB)")
    if args.article:
        print(f"  文章: {args.article}")
    print(f"  CDP:  {args.cdp_url}")
    print(f"  模式: {'发布' if args.publish else '草稿'}")
    print()

    # ── Phase 1: 连接视频号创作者中心 ──
    print("▶ Phase 1: 连接视频号创作者中心")
    tab = navigate_to_channels(args.cdp_url)
    if not tab:
        print("✗ 无法连接视频号创作者中心")
        print("  请确保：")
        print("  1. Chrome 已启动并启用 Remote Debugging")
        print("  2. 已在浏览器中登录 channels.weixin.qq.com")
        sys.exit(1)

    cdp = connect_tab(tab)
    uploader = ChannelsUploader(cdp)

    try:
        # 检查登录状态
        if not uploader.check_login_status():
            print("⚠ 可能未登录视频号创作者中心")
            print("  请在浏览器中登录后重试")
            # 不强制退出，继续尝试

        # ── Phase 2: 上传视频 ──
        print("\n▶ Phase 2: 上传视频")
        if not uploader.upload_video(args.video):
            print("✗ 视频上传失败")
            sys.exit(1)

        # ── Phase 3: 填写元数据 ──
        print("\n▶ Phase 3: 填写元数据")

        # 标题
        title = args.title
        if not title and args.article:
            content = load_article_content(args.article)
            if content:
                try:
                    from metadata_generator import generate_title
                    print("  🤖 AI 生成标题...")
                    title = generate_title(content)
                    print(f"  ✓ 标题: {title}")
                except Exception as e:
                    print(f"  ⚠ AI 标题生成失败: {e}")

        if title:
            uploader.fill_title(title)

        # 描述
        desc = args.desc
        if not desc and args.article:
            content = content if 'content' in dir() else load_article_content(args.article)
            if content:
                try:
                    from metadata_generator import generate_description
                    print("  🤖 AI 生成描述...")
                    desc = generate_description(content)
                    print(f"  ✓ 描述: {desc[:80]}...")
                except Exception as e:
                    print(f"  ⚠ AI 描述生成失败: {e}")

        if desc:
            uploader.fill_description(desc)

        # 封面：优先用户指定 → 智能截取 → 平台默认
        cover_path = args.cover
        if not cover_path and not args.no_auto_cover:
            try:
                print("  🖼️ 智能封面截取...")
                cover_path = extract_smart_cover(
                    video_path=args.video,
                    output_path=os.path.join(SCRIPT_DIR, "auto_cover.jpg"),
                    target_ratio="16:9",
                    article_title=title or "",
                )
            except Exception as e:
                print(f"  ⚠ 智能封面截取失败: {e}，将使用平台默认截图")

        if cover_path:
            uploader.upload_cover(cover_path)

        # ── Phase 4: 保存/发布 ──
        print(f"\n▶ Phase 4: {'发布' if args.publish else '保存草稿'}")
        if args.publish:
            success = uploader.publish()
        else:
            success = uploader.save_draft()

        # ── 总结 ──
        print()
        print(f"📋 视频号发布总结")
        print(f"━━━━━━━━━━━━━━━━━━━━")
        print(f"  视频: {os.path.basename(args.video)} ({size_mb:.1f} MB)")
        if title:
            print(f"  标题: {title}")
        if desc:
            print(f"  描述: {desc[:60]}...")
        print(f"  封面: {'自定义' if args.cover else ('智能截取' if cover_path else '平台默认')}")
        print(f"  模式: {'已发布' if args.publish else '已保存草稿'}")
        print(f"  状态: {'✅ 完成' if success else '⚠ 部分完成，请到创作者中心确认'}")
        print(f"━━━━━━━━━━━━━━━━━━━━")

        if not args.publish:
            print("\n💡 草稿已保存，请到 channels.weixin.qq.com 确认后手动发布")

    finally:
        cdp.close()


if __name__ == "__main__":
    main()
