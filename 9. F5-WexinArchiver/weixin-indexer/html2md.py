#!/usr/bin/env python3
"""
将微信公众号 HTML 备份文章批量转换为 Markdown 格式。
输出目录: 历史备份_md/YYYY-MM/文件名.md

用法: python3 html2md.py
"""
import os
import re
import json
import html as html_module
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "历史备份")
OUTPUT_DIR = os.path.join(BASE_DIR, "历史备份_md")
INDEX_FILE = os.path.join(BASE_DIR, "articles_index.json")


def html_to_markdown(soup_element):
    """将 BeautifulSoup 元素递归转换为 Markdown 文本。"""
    if soup_element is None:
        return ""

    parts = []
    for child in soup_element.children:
        if isinstance(child, str):
            # NavigableString
            text = child.strip()
            if text:
                parts.append(text)
            elif child == '\n':
                pass  # skip bare newlines
            continue

        tag = child.name
        if tag is None:
            continue

        # 跳过 script/style
        if tag in ('script', 'style', 'noscript'):
            continue

        # 图片
        if tag == 'img':
            src = child.get('data-src') or child.get('src') or ''
            alt = child.get('alt', '')
            if src:
                parts.append(f"\n![{alt}]({src})\n")
            continue

        # 换行
        if tag == 'br':
            parts.append("\n")
            continue

        # 水平线
        if tag == 'hr':
            parts.append("\n---\n")
            continue

        # 递归获取子内容
        inner = html_to_markdown(child)

        # 标题 h1-h6
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            hashes = '#' * level
            parts.append(f"\n{hashes} {inner.strip()}\n")
            continue

        # 段落
        if tag == 'p':
            text = inner.strip()
            if text:
                parts.append(f"\n{text}\n")
            continue

        # 加粗
        if tag in ('strong', 'b'):
            text = inner.strip()
            if text:
                parts.append(f"**{text}**")
            continue

        # 斜体
        if tag in ('em', 'i'):
            text = inner.strip()
            if text:
                parts.append(f"*{text}*")
            continue

        # 链接
        if tag == 'a':
            href = child.get('href', '')
            text = inner.strip()
            if text and href:
                parts.append(f"[{text}]({href})")
            elif text:
                parts.append(text)
            continue

        # 列表
        if tag == 'ul':
            items = child.find_all('li', recursive=False)
            for item in items:
                item_text = html_to_markdown(item).strip()
                parts.append(f"\n- {item_text}")
            parts.append("\n")
            continue

        if tag == 'ol':
            items = child.find_all('li', recursive=False)
            for idx, item in enumerate(items, 1):
                item_text = html_to_markdown(item).strip()
                parts.append(f"\n{idx}. {item_text}")
            parts.append("\n")
            continue

        # 引用
        if tag == 'blockquote':
            lines = inner.strip().split('\n')
            quoted = '\n'.join(f"> {line}" for line in lines)
            parts.append(f"\n{quoted}\n")
            continue

        # 代码块
        if tag == 'pre':
            code = inner.strip()
            parts.append(f"\n```\n{code}\n```\n")
            continue

        if tag == 'code':
            text = inner.strip()
            if text:
                parts.append(f"`{text}`")
            continue

        # section / div / span 等容器标签，直接递归
        if tag in ('section', 'div', 'span', 'article', 'main',
                    'header', 'footer', 'figure', 'figcaption',
                    'li', 'td', 'th', 'tr', 'thead', 'tbody',
                    'table', 'sup', 'sub', 'u', 'del', 'mark',
                    'details', 'summary', 'label', 'fieldset',
                    'legend', 'nav', 'aside', 'time', 'abbr',
                    'cite', 'dfn', 'kbd', 'samp', 'var',
                    'ruby', 'rt', 'rp', 'bdi', 'bdo', 'wbr',
                    'data', 'output', 'progress', 'meter',
                    'dialog', 'slot', 'template', 'picture',
                    'source', 'track', 'map', 'area', 'svg',
                    'math', 'mtext', 'mi', 'mo', 'mn', 'ms',
                    'mrow', 'msup', 'msub', 'mfrac', 'mroot',
                    'msqrt', 'mtable', 'mtr', 'mtd', 'mth',
                    'font', 'center', 'small', 'big', 'tt',
                    'strike', 's', 'nobr', 'iframe', 'embed',
                    'object', 'param', 'video', 'audio',
                    'canvas', 'form', 'input', 'textarea',
                    'select', 'option', 'button', 'datalist',
                    'optgroup', 'colgroup', 'col', 'caption',
                    'tfoot', 'dd', 'dt', 'dl', 'address',
                    'hgroup', 'menu', 'menuitem', 'command',
                    'keygen', 'multicol', 'spacer', 'listing',
                    'xmp', 'nextid', 'isindex', 'basefont',
                    'dir', 'applet', 'bgsound', 'blink',
                    'comment', 'ilayer', 'layer', 'marquee',
                    'noembed', 'nolayer', 'plaintext',
                    'rb', 'rtc'):
            if inner.strip():
                parts.append(inner)
            continue

        # 其他未知标签，也递归
        if inner.strip():
            parts.append(inner)

    return ''.join(parts)


def clean_markdown(text):
    """清理 Markdown 文本，去除多余空行等。"""
    # 去除连续多个空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 去除行尾空格
    text = re.sub(r' +\n', '\n', text)
    # 去除开头空行
    text = text.strip()
    return text


def convert_one(html_path, output_path, title="", date="", url=""):
    """将单个 HTML 文件转换为 Markdown。"""
    with open(html_path, 'r', encoding='utf-8') as f:
        raw = f.read()

    soup = BeautifulSoup(raw, 'html.parser')

    # 提取正文区域
    content = soup.find(id='js_content')
    if content is None:
        content = soup.find(class_='rich_media_content')
    if content is None:
        # fallback: 尝试 body
        content = soup.find('body')
    if content is None:
        print(f"  [SKIP] 无法找到正文: {html_path}")
        return False

    md_body = html_to_markdown(content)
    md_body = clean_markdown(md_body)

    if len(md_body) < 50:
        print(f"  [SKIP] 正文过短({len(md_body)}字): {html_path}")
        return False

    # 组装 Markdown 文件
    header = f"# {title}\n\n"
    if date:
        header += f"> 日期: {date}  \n"
    if url:
        header += f"> 原文链接: [{title}]({url})  \n"
    header += f"> 来源: 薛以致用 微信公众号  \n\n---\n\n"

    full_md = header + md_body

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_md)

    return True


def main():
    # 加载文章索引
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    # 建立 title -> article 映射
    title_map = {}
    for art in articles:
        title_map[art['title']] = art

    total = 0
    converted = 0
    skipped = 0

    # 遍历所有月份目录
    if not os.path.isdir(BACKUP_DIR):
        print(f"备份目录不存在: {BACKUP_DIR}")
        return

    months = sorted(os.listdir(BACKUP_DIR))
    for month in months:
        month_path = os.path.join(BACKUP_DIR, month)
        if not os.path.isdir(month_path):
            continue

        files = sorted(f for f in os.listdir(month_path) if f.endswith('.html'))
        for fname in files:
            total += 1
            html_path = os.path.join(month_path, fname)

            # 从文件名提取日期和标题
            # 格式: YYYY-MM-DD_标题.html
            match = re.match(r'(\d{4}-\d{2}-\d{2})_(.+)\.html$', fname)
            if match:
                file_date = match.group(1)
                file_title = match.group(2)
            else:
                file_date = month
                file_title = fname.replace('.html', '')

            # 尝试从索引中匹配
            art_info = None
            for art in articles:
                if art['date'] == file_date and art['title'][:8] in file_title:
                    art_info = art
                    break
            if art_info is None:
                # 模糊匹配
                for art in articles:
                    if file_title[:10] in art['title'] or art['title'][:10] in file_title:
                        art_info = art
                        break

            title = art_info['title'] if art_info else file_title
            date = art_info['date'] if art_info else file_date
            url = art_info.get('url', '') if art_info else ''

            # 输出路径
            out_fname = fname.replace('.html', '.md')
            out_path = os.path.join(OUTPUT_DIR, month, out_fname)

            ok = convert_one(html_path, out_path, title=title, date=date, url=url)
            if ok:
                converted += 1
            else:
                skipped += 1

    print(f"\n转换完成: 共 {total} 个文件, 成功 {converted}, 跳过 {skipped}")
    print(f"输出目录: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
