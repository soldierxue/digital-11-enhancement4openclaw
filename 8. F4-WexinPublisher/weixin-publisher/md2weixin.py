#!/usr/bin/env python3
"""
md2weixin.py — Markdown → 微信公众号 HTML 转换
基于 weixin-inline-template.html 的样式规范，为所有元素添加 inline style
"""

import os
import re
import markdown
from bs4 import BeautifulSoup, NavigableString

# ── 从模板提取的 inline style 定义 ──

SECTION_STYLE = (
    "box-sizing: border-box; max-width: 680px; margin: 0 auto; "
    "padding: 20px 16px; background-color: #ffffff; color: #1F2328; "
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', "
    "Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji'; "
    "font-size: 16px; line-height: 1.75; word-wrap: break-word; letter-spacing: 0.5px;"
)

P_STYLE = (
    "margin: 0 0 16px 0; padding: 0; font-size: 16px; "
    "line-height: 1.75; color: #1F2328; letter-spacing: 0.5px;"
)

H2_STYLE = (
    "margin: 32px 0 16px 0; padding: 0 0 8px 0; font-size: 22px; "
    "font-weight: 600; line-height: 1.3; color: #1F2328; "
    "border-bottom: 1px solid #d0d7de;"
)

H3_STYLE = (
    "margin: 28px 0 14px 0; padding: 0; font-size: 19px; "
    "font-weight: 600; line-height: 1.3; color: #1F2328;"
)

H4_STYLE = (
    "margin: 24px 0 12px 0; padding: 0; font-size: 16px; "
    "font-weight: 600; line-height: 1.3; color: #1F2328;"
)

H1_STYLE = (
    "margin: 0 0 24px 0; padding: 0 0 12px 0; font-size: 24px; "
    "font-weight: 600; line-height: 1.3; color: #1F2328; "
    "border-bottom: 1px solid #d0d7de;"
)

STRONG_STYLE = "font-weight: 600; color: #1F2328;"

A_STYLE = "color: #0969da; text-decoration: none;"

INLINE_CODE_STYLE = (
    "padding: 2px 6px; margin: 0 2px; font-size: 14px; "
    "font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
    "'Liberation Mono', monospace; background-color: rgba(175, 184, 193, 0.2); "
    "border-radius: 4px; color: #1F2328; white-space: break-spaces;"
)

PRE_STYLE = (
    "margin: 0 0 16px 0; padding: 16px; font-size: 14px; "
    "font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
    "'Liberation Mono', monospace; line-height: 1.45; color: #1F2328; "
    "background-color: #f6f8fa; border-radius: 6px; overflow-x: auto; "
    "white-space: pre; word-wrap: normal;"
)

PRE_CODE_STYLE = (
    "padding: 0; margin: 0; font-size: 14px; "
    "font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
    "'Liberation Mono', monospace; background: transparent; border: 0; "
    "white-space: pre;"
)

BLOCKQUOTE_STYLE = (
    "margin: 0 0 16px 0; padding: 8px 16px; color: #656d76; "
    "border-left: 4px solid #d0d7de; background-color: #f6f8fa;"
)

BLOCKQUOTE_P_STYLE = (
    "margin: 0; padding: 0; font-size: 15px; line-height: 1.75; "
    "color: #656d76; letter-spacing: 0.5px;"
)

UL_STYLE = (
    "margin: 0 0 16px 0; padding-left: 2em; font-size: 16px; "
    "line-height: 1.75; color: #1F2328;"
)

OL_STYLE = UL_STYLE

LI_STYLE = "margin: 4px 0; letter-spacing: 0.5px;"

HR_STYLE = (
    "margin: 24px 0; padding: 0; height: 1px; "
    "background-color: #d0d7de; border: 0; overflow: hidden;"
)

IMG_STYLE = "max-width: 100%; border-radius: 4px; box-sizing: border-box;"

TABLE_STYLE = (
    "margin: 0 0 16px 0; border-spacing: 0; border-collapse: collapse; "
    "width: 100%; font-size: 15px; line-height: 1.6; overflow: auto;"
)

TH_STYLE = (
    "padding: 8px 13px; border: 1px solid #d0d7de; "
    "font-weight: 600; text-align: left;"
)

TD_STYLE = "padding: 8px 13px; border: 1px solid #d0d7de;"

DEL_STYLE = "text-decoration: line-through; color: #656d76;"


def _apply_inline_styles(soup: BeautifulSoup) -> None:
    """遍历 HTML 树，为每个元素添加对应的 inline style"""

    # 标题
    for tag in soup.find_all("h1"):
        tag["style"] = H1_STYLE
    for tag in soup.find_all("h2"):
        tag["style"] = H2_STYLE
    for tag in soup.find_all("h3"):
        tag["style"] = H3_STYLE
    for tag in soup.find_all("h4"):
        tag["style"] = H4_STYLE

    # 引用块（先处理，因为内部 p 需要特殊样式）
    for bq in soup.find_all("blockquote"):
        bq["style"] = BLOCKQUOTE_STYLE
        for p in bq.find_all("p"):
            p["style"] = BLOCKQUOTE_P_STYLE

    # 段落（排除 blockquote 内的 p，已在上面处理）
    for tag in soup.find_all("p"):
        if tag.parent and tag.parent.name == "blockquote":
            continue
        tag["style"] = P_STYLE

    # 代码块 pre > code
    for pre in soup.find_all("pre"):
        pre["style"] = PRE_STYLE
        code = pre.find("code")
        if code:
            code["style"] = PRE_CODE_STYLE

    # 行内代码（排除 pre 内的 code）
    for code in soup.find_all("code"):
        if code.parent and code.parent.name == "pre":
            continue
        code["style"] = INLINE_CODE_STYLE

    # 加粗
    for tag in soup.find_all("strong"):
        tag["style"] = STRONG_STYLE

    # 链接
    for tag in soup.find_all("a"):
        tag["style"] = A_STYLE

    # 列表
    for tag in soup.find_all("ul"):
        tag["style"] = UL_STYLE
    for tag in soup.find_all("ol"):
        tag["style"] = OL_STYLE
    for tag in soup.find_all("li"):
        tag["style"] = LI_STYLE

    # 分割线
    for tag in soup.find_all("hr"):
        tag["style"] = HR_STYLE

    # 图片
    for tag in soup.find_all("img"):
        tag["style"] = IMG_STYLE

    # 表格
    for tag in soup.find_all("table"):
        tag["style"] = TABLE_STYLE
    for i, tr in enumerate(soup.find_all("tr")):
        if tr.parent and tr.parent.name == "thead":
            tr["style"] = "background-color: #f6f8fa; border-top: 1px solid #d0d7de;"
        else:
            bg = "#ffffff" if i % 2 == 0 else "#f6f8fa"
            tr["style"] = f"background-color: {bg}; border-top: 1px solid #d0d7de;"
    for tag in soup.find_all("th"):
        tag["style"] = TH_STYLE
    for tag in soup.find_all("td"):
        tag["style"] = TD_STYLE

    # 删除线
    for tag in soup.find_all("del"):
        tag["style"] = DEL_STYLE


def _load_disclaimer() -> str:
    """加载 disclaimer HTML 模板（文章底部标准声明）"""
    disclaimer_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "markdown_html_template", "disclaimer.html"
    )
    if os.path.exists(disclaimer_path):
        with open(disclaimer_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def md_to_weixin_html(markdown_text: str, image_map: dict = None,
                      related_html: str = None,
                      append_disclaimer: bool = True) -> str:
    """
    将 Markdown 转换为微信公众号兼容 HTML（带 inline style）

    参数:
        markdown_text: Markdown 正文
        image_map: {原始图片路径/URL: 微信URL} 映射表（可选）
        related_html: 扩展阅读推荐 HTML 块（可选，插入在 disclaimer 之前）
        append_disclaimer: 是否在文末追加标准 disclaimer 声明（默认 True）

    返回:
        微信兼容的 HTML 字符串（section 包裹，所有元素带 inline style）
    """
    # Markdown → HTML
    extensions = ["tables", "fenced_code", "nl2br"]
    html = markdown.markdown(markdown_text, extensions=extensions)

    # 替换图片 URL
    if image_map:
        for original_url, weixin_url in image_map.items():
            html = html.replace(original_url, weixin_url)

    # 解析并添加 inline style
    soup = BeautifulSoup(html, "html.parser")
    _apply_inline_styles(soup)

    # 包裹在 section 容器中
    content = soup.decode_contents()

    # 追加扩展阅读（已带 inline style，直接拼接）
    related = related_html or ""

    # 追加 disclaimer（已带 inline style，直接拼接）
    disclaimer = ""
    if append_disclaimer:
        disclaimer = _load_disclaimer()

    return f'<section style="{SECTION_STYLE}">{content}{related}{disclaimer}</section>'


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python md2weixin.py <markdown文件路径>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        md_text = f.read()

    # 去掉 front-matter
    md_text = re.sub(r'^---\s*\n.*?\n---\s*\n', '', md_text, flags=re.DOTALL)

    html = md_to_weixin_html(md_text)
    print(html)
