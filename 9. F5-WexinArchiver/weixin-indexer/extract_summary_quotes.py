#!/usr/bin/env python3
"""
从 Markdown 格式文章中提取 Executive Summary 和金句。
读取 历史备份_md/ 下所有 .md 文件，输出汇总到 文章摘要与金句.md

金句提取策略:
1. **加粗文本** (Markdown bold) — 作者刻意强调的内容
2. > 引用块 — 通常是精华观点
3. 短句独立成段（<80字）且包含感叹号/问号 — 通常是观点性金句
4. 包含特定关键词的句子（如"核心"、"本质"、"关键"、"真正"等）

Executive Summary 策略:
- 取文章前 600 字（去除标题和元信息后）作为摘要基础
- 如果文章有明确的摘要段落（开头的非标题段落），优先使用

用法: python3 extract_summary_quotes.py
"""
import os
import re
import json
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MD_DIR = os.path.join(BASE_DIR, "历史备份_md")
INDEX_FILE = os.path.join(BASE_DIR, "articles_index.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "文章摘要与金句.md")

# 金句关键词（出现在短句中增加金句概率）
QUOTE_KEYWORDS = [
    '核心', '本质', '关键', '真正', '最重要', '唯一', '根本',
    '不是.*而是', '从来不是', '永远', '终将', '必须', '决定',
    '未来', '时代', '革命', '颠覆', '重塑', '重构', '重新定义',
    '赢家', '输家', '选择', '代价', '机会', '危机',
    '第一', '最大', '最好', '最坏', '最后',
    '记住', '别忘了', '千万', '务必', '切记',
]


def extract_quotes_from_md(md_text):
    """从 Markdown 文本中提取金句。返回去重后的金句列表。"""
    quotes = []
    seen = set()

    def add_quote(q):
        q = q.strip()
        # 清理 markdown 标记
        q = re.sub(r'\*\*', '', q)
        q = re.sub(r'\*', '', q)
        q = re.sub(r'^>\s*', '', q)
        q = re.sub(r'^#+\s*', '', q)
        q = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', q)  # 去链接
        q = re.sub(r'!\[.*?\]\(.*?\)', '', q)  # 去图片
        q = q.strip()
        if len(q) < 8 or len(q) > 200:
            return
        # 过滤纯日期、纯数字、纯链接等
        if re.match(r'^[\d\-\./\s]+$', q):
            return
        if q.startswith('http'):
            return
        if q.startswith('日期:') or q.startswith('原文链接:') or q.startswith('来源:'):
            return
        key = q[:30]
        if key not in seen:
            seen.add(key)
            quotes.append(q)

    lines = md_text.split('\n')

    # 策略1: 提取加粗文本
    bold_pattern = re.compile(r'\*\*(.+?)\*\*')
    for line in lines:
        bolds = bold_pattern.findall(line)
        for b in bolds:
            b = b.strip()
            if len(b) >= 8 and len(b) <= 200:
                # 过滤纯格式性加粗（如标题重复、数字等）
                if not re.match(r'^[\d¥$€£\s\.\,]+$', b):
                    add_quote(b)

    # 策略2: 提取引用块
    in_quote = False
    quote_buf = []
    for line in lines:
        if line.startswith('>'):
            content = line.lstrip('>').strip()
            if content and not content.startswith('日期') and not content.startswith('原文') and not content.startswith('来源'):
                quote_buf.append(content)
            in_quote = True
        else:
            if in_quote and quote_buf:
                full_quote = ' '.join(quote_buf)
                add_quote(full_quote)
                quote_buf = []
            in_quote = False
    if quote_buf:
        full_quote = ' '.join(quote_buf)
        add_quote(full_quote)

    # 策略3: 短句独立成段且有感叹号/问号
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        if line_clean.startswith('#') or line_clean.startswith('>') or line_clean.startswith('!'):
            continue
        if line_clean.startswith('---'):
            continue
        # 去除 markdown 标记后的纯文本
        plain = re.sub(r'\*\*', '', line_clean)
        plain = re.sub(r'\*', '', plain)
        plain = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', plain)
        plain = plain.strip()
        if 10 <= len(plain) <= 100:
            if re.search(r'[！？!?]$', plain) or re.search(r'[。；]$', plain):
                # 检查是否包含观点性内容
                has_keyword = any(re.search(kw, plain) for kw in QUOTE_KEYWORDS)
                if has_keyword or re.search(r'[！!]', plain):
                    add_quote(plain)

    # 策略4: 包含关键词的完整句子
    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('#') or line_clean.startswith('---'):
            continue
        plain = re.sub(r'\*\*', '', line_clean)
        plain = re.sub(r'\*', '', plain)
        plain = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', plain)
        plain = re.sub(r'!\[.*?\]\(.*?\)', '', plain)
        plain = plain.strip()
        # 分句
        sentences = re.split(r'[。；！？!?]', plain)
        for sent in sentences:
            sent = sent.strip()
            if 15 <= len(sent) <= 120:
                keyword_count = sum(1 for kw in QUOTE_KEYWORDS if re.search(kw, sent))
                if keyword_count >= 2:
                    add_quote(sent)

    return quotes


def extract_summary(md_text, max_chars=600):
    """从 Markdown 文本中提取 Executive Summary。"""
    lines = md_text.split('\n')

    # 跳过 frontmatter (标题、元信息、分隔线)
    body_start = 0
    found_separator = False
    for i, line in enumerate(lines):
        if line.strip() == '---' and i > 0:
            if not found_separator:
                found_separator = True
                continue
            else:
                body_start = i + 1
                break
        if found_separator and line.strip() == '---':
            body_start = i + 1
            break

    if body_start == 0:
        # 没有找到分隔线，跳过前5行（通常是标题和元信息）
        body_start = min(5, len(lines))

    # 收集正文段落
    paragraphs = []
    current_para = []
    for line in lines[body_start:]:
        stripped = line.strip()
        if not stripped:
            if current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
            continue
        # 跳过图片、分隔线
        if stripped.startswith('![') or stripped == '---':
            continue
        # 跳过标题行（但保留内容）
        if stripped.startswith('#'):
            if current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
            continue
        # 清理 markdown
        clean = re.sub(r'\*\*', '', stripped)
        clean = re.sub(r'\*', '', clean)
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
        clean = re.sub(r'^>\s*', '', clean)
        clean = clean.strip()
        if clean:
            current_para.append(clean)

    if current_para:
        paragraphs.append(' '.join(current_para))

    # 拼接前几段作为摘要
    summary = ''
    for para in paragraphs:
        if len(summary) + len(para) > max_chars:
            remaining = max_chars - len(summary)
            if remaining > 50:
                summary += para[:remaining] + '...'
            break
        summary += para + '\n'
        if len(summary) >= max_chars * 0.7:
            break

    return summary.strip()


def main():
    # 加载文章索引
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    # 建立日期+标题前缀 -> article 映射
    art_map = {}
    for art in articles:
        key = f"{art['date']}_{art['title'][:8]}"
        art_map[key] = art

    # 收集所有 md 文件
    md_files = sorted(glob.glob(os.path.join(MD_DIR, '**', '*.md'), recursive=True))

    results = []

    for md_path in md_files:
        with open(md_path, 'r', encoding='utf-8') as f:
            md_text = f.read()

        # 从文件名提取信息
        fname = os.path.basename(md_path)
        match = re.match(r'(\d{4}-\d{2}-\d{2})_(.+)\.md$', fname)
        if match:
            file_date = match.group(1)
            file_title = match.group(2)
        else:
            continue

        # 匹配索引
        art_info = None
        for art in articles:
            if art['date'] == file_date and art['title'][:8] in file_title:
                art_info = art
                break
        if art_info is None:
            for art in articles:
                if file_title[:10] in art.get('title', ''):
                    art_info = art
                    break

        title = art_info['title'] if art_info else file_title
        date = art_info['date'] if art_info else file_date

        # 提取摘要和金句
        summary = extract_summary(md_text)
        quotes = extract_quotes_from_md(md_text)

        if not summary and not quotes:
            continue

        # 计算相对路径
        rel_path = os.path.relpath(md_path, BASE_DIR)

        results.append({
            'title': title,
            'date': date,
            'summary': summary,
            'quotes': quotes,
            'path': rel_path,
        })

    # 按日期倒序排列
    results.sort(key=lambda x: x['date'], reverse=True)

    # 输出 Markdown 文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 微信公众号「薛以致用」文章摘要与金句\n\n")
        f.write("> 自动从 Markdown 格式文章中提取，共 {} 篇文章\n\n".format(len(results)))
        f.write("---\n\n")

        for i, r in enumerate(results, 1):
            f.write(f"## {i}. {r['title']}（{r['date']}）\n\n")
            f.write(f"📄 [查看全文]({r['path']})\n\n")

            if r['summary']:
                f.write(f"### Executive Summary\n\n")
                f.write(f"{r['summary']}\n\n")

            if r['quotes']:
                f.write(f"### 金句摘录\n\n")
                for q in r['quotes']:
                    f.write(f"- 💬 「{q}」\n")
                f.write("\n")

            f.write("---\n\n")

    print(f"完成！共处理 {len(results)} 篇文章")
    print(f"输出文件: {OUTPUT_FILE}")

    # 统计
    total_quotes = sum(len(r['quotes']) for r in results)
    avg_quotes = total_quotes / len(results) if results else 0
    print(f"共提取 {total_quotes} 条金句，平均每篇 {avg_quotes:.1f} 条")


if __name__ == '__main__':
    main()
