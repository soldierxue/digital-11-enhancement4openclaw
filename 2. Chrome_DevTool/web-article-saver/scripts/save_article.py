#!/usr/bin/env python3
"""
save_article.py — 从用户浏览器抓取文章（含图片），保存为 Markdown + PDF。
通过 CDP (Chrome DevTools Protocol) 直接在浏览器上下文中 fetch 图片，绕过防盗链。

用法:
    python3 save_article.py [选项]

选项:
    --cdp-url URL       CDP 端口地址 (默认: http://127.0.0.1:9222)
    --tab-url PATTERN   匹配标签页 URL 的关键词 (默认: 使用第一个 page 标签)
    --output-dir DIR    保存目录 (默认: ~/Artical/Weixin)
    --format FMT        输出格式: md, pdf, both (默认: both)
    --no-images         不下载图片
    --scroll            滚动页面触发懒加载 (默认: 是)

支持的网站:
    - 微信公众号 (mp.weixin.qq.com) — 有防盗链
    - 知乎文章/专栏 (zhuanlan.zhihu.com)
    - 任意网页 (通用模式)
"""

import json
import subprocess
import os
import sys
import time
import base64
import hashlib
import argparse
import re

try:
    import websocket
except ImportError:
    print("ERROR: 需要 websocket-client。运行: pip3 install --break-system-packages websocket-client")
    sys.exit(1)


# ============================================================
# 站点适配器
# ============================================================

SITE_ADAPTERS = {
    "mp.weixin.qq.com": {
        "name": "微信公众号",
        "title_selector": "#activity-name",
        "author_selector": "#js_name",
        "content_selector": "#js_content",
        "has_lazy_load": True,
        "anti_hotlink": True,
    },
    "zhuanlan.zhihu.com": {
        "name": "知乎专栏",
        "title_selector": ".Post-Title",
        "author_selector": ".AuthorInfo-name",
        "content_selector": ".Post-RichTextContainer",
        "has_lazy_load": True,
        "anti_hotlink": False,
    },
}

DEFAULT_ADAPTER = {
    "name": "通用网页",
    "title_selector": "h1, .title, .article-title",
    "author_selector": ".author, .byline, [rel='author']",
    "content_selector": "article, .article-content, .post-content, .entry-content, main, body",
    "has_lazy_load": False,
    "anti_hotlink": False,
}


def get_adapter(url):
    for domain, adapter in SITE_ADAPTERS.items():
        if domain in url:
            return adapter
    return DEFAULT_ADAPTER


# ============================================================
# CDP 通信
# ============================================================

class CDPClient:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.msg_id = 0

    def send(self, method, params=None):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self.msg_id:
                return resp
            # skip events

    def evaluate(self, expression, await_promise=False):
        params = {"expression": expression, "returnByValue": True}
        if await_promise:
            params["awaitPromise"] = True
        resp = self.send("Runtime.evaluate", params)
        return resp.get("result", {}).get("result", {}).get("value")

    def close(self):
        self.ws.close()


def find_tab(cdp_url, tab_url_pattern=None):
    """查找匹配的标签页"""
    result = subprocess.run(
        ["curl", "-s", f"{cdp_url}/json/list"],
        capture_output=True, text=True, timeout=5
    )
    tabs = json.loads(result.stdout)
    pages = [t for t in tabs if t.get("type") == "page"]

    if not pages:
        return None

    if tab_url_pattern:
        for t in pages:
            if tab_url_pattern in t.get("url", ""):
                return t

    # 返回第一个非 about:blank 页面
    for t in pages:
        if t.get("url", "") != "about:blank" and not t.get("url", "").startswith("chrome://"):
            return t

    return pages[0] if pages else None


# ============================================================
# 文章抓取
# ============================================================

def trigger_lazy_load(cdp):
    """滚动页面触发懒加载"""
    cdp.evaluate("""
    (async () => {
        const delay = ms => new Promise(r => setTimeout(r, ms));
        const totalHeight = document.body.scrollHeight;
        for (let y = 0; y < totalHeight; y += 500) {
            window.scrollTo(0, y);
            await delay(200);
        }
        window.scrollTo(0, 0);
        await delay(300);
        // 强制替换 data-src -> src
        document.querySelectorAll('img[data-src]').forEach(img => {
            if (!img.src || img.naturalWidth <= 1) {
                img.src = img.getAttribute('data-src');
            }
        });
        return 'done';
    })()
    """, await_promise=True)
    time.sleep(3)


def extract_article(cdp, adapter):
    """提取文章标题、作者、HTML 和段落"""
    js = f"""
    (() => {{
        const q = s => document.querySelector(s);
        const title = (() => {{
            const selectors = "{adapter['title_selector']}".split(',').map(s => s.trim());
            for (const s of selectors) {{
                const el = q(s);
                if (el && el.textContent.trim()) return el.textContent.trim();
            }}
            return document.title;
        }})();

        const author = (() => {{
            const selectors = "{adapter['author_selector']}".split(',').map(s => s.trim());
            for (const s of selectors) {{
                const el = q(s);
                if (el && el.textContent.trim()) return el.textContent.trim();
            }}
            return '';
        }})();

        const contentEl = (() => {{
            const selectors = "{adapter['content_selector']}".split(',').map(s => s.trim());
            for (const s of selectors) {{
                const el = q(s);
                if (el) return el;
            }}
            return document.body;
        }})();

        const html = contentEl.innerHTML;
        const images = [];
        contentEl.querySelectorAll('img').forEach((img, i) => {{
            const src = img.getAttribute('data-src') || img.src || '';
            if (src && !src.startsWith('data:')) {{
                images.push({{index: i, src: src, alt: img.alt || ''}});
            }}
        }});

        // 按段落提取文本
        const paragraphs = [];
        contentEl.querySelectorAll('p, section, h1, h2, h3, h4, blockquote, pre, li, figcaption').forEach(el => {{
            const text = el.innerText?.trim();
            if (text) paragraphs.push({{tag: el.tagName.toLowerCase(), text}});
        }});

        return JSON.stringify({{title, author, html, images, paragraphs}});
    }})()
    """
    raw = cdp.evaluate(js)
    return json.loads(raw)


def download_images(cdp, images, img_dir):
    """通过浏览器上下文 fetch 图片（绕过防盗链）"""
    os.makedirs(img_dir, exist_ok=True)
    img_map = {}

    for img in images:
        src = img["src"]
        fname = f"img_{img['index']:02d}_{hashlib.md5(src.encode()).hexdigest()[:8]}"

        fetch_js = f"""
        (async () => {{
            try {{
                const resp = await fetch("{src}");
                const blob = await resp.blob();
                return new Promise((resolve) => {{
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result);
                    reader.readAsDataURL(blob);
                }});
            }} catch(e) {{
                return 'ERROR:' + e.message;
            }}
        }})()
        """
        data_url = cdp.evaluate(fetch_js, await_promise=True)

        if data_url and not str(data_url).startswith("ERROR") and "base64," in str(data_url):
            header, b64data = data_url.split("base64,", 1)
            ext = "png"
            if "jpeg" in header or "jpg" in header:
                ext = "jpg"
            elif "gif" in header:
                ext = "gif"
            elif "webp" in header:
                ext = "webp"

            fpath = os.path.join(img_dir, f"{fname}.{ext}")
            with open(fpath, "wb") as f:
                f.write(base64.b64decode(b64data))

            if os.path.getsize(fpath) > 200:
                img_map[src] = fpath
                print(f"  ✔ [{img['index']}] {os.path.getsize(fpath)/1024:.1f}KB → {fname}.{ext}")
            else:
                os.remove(fpath)
        else:
            print(f"  ✘ [{img['index']}] 下载失败")

    return img_map


def safe_filename(title):
    """生成安全的文件名"""
    name = re.sub(r'[<>:"/\\|?*\n\r]', '', title).strip()
    return name[:200] if name else "untitled"


def generate_markdown(article, url, img_map, save_dir):
    """生成含本地图片引用的 Markdown"""
    lines = [
        f"# {article['title']}\n",
        f"> 作者: {article['author']}" if article['author'] else "",
        f"> 来源: {url.split('?')[0]}\n",
    ]

    for p in article.get("paragraphs", []):
        tag = p["tag"]
        text = p["text"]
        if tag in ("h1", "h2", "h3", "h4"):
            level = "#" * int(tag[1])
            lines.append(f"\n{level} {text}\n")
        elif tag == "blockquote":
            lines.append(f"\n> {text}\n")
        elif tag == "pre":
            lines.append(f"\n```\n{text}\n```\n")
        elif tag == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)
            lines.append("")

    if img_map:
        lines.append("\n---\n## 文章图片\n")
        for i, (src, local_path) in enumerate(img_map.items()):
            rel_path = os.path.relpath(local_path, save_dir)
            lines.append(f"![图片{i+1}]({rel_path})\n")

    return "\n".join(lines)


def generate_pdf(cdp, article_html, img_map):
    """生成图片内嵌的 PDF"""
    html = article_html
    for src, local_path in img_map.items():
        with open(local_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = local_path.rsplit(".", 1)[-1]
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "gif": "image/gif", "webp": "image/webp"}
        data_uri = f"data:{mime_map.get(ext, 'image/png')};base64,{b64}"
        html = html.replace(src, data_uri)

    inject_js = f"""
    (() => {{
        const selectors = ['#js_content', 'article', '.article-content', '.post-content', 'main'];
        let el = null;
        for (const s of selectors) {{
            el = document.querySelector(s);
            if (el) break;
        }}
        if (el) el.innerHTML = {json.dumps(html)};
        document.querySelectorAll('img').forEach(img => {{
            img.style.visibility = 'visible';
            img.style.display = 'block';
            if (img.getAttribute('data-src') && !img.src.startsWith('data:')) {{
                img.src = img.getAttribute('data-src');
            }}
        }});
        return 'ok';
    }})()
    """
    cdp.evaluate(inject_js)
    time.sleep(2)

    resp = cdp.send("Page.printToPDF", {
        "printBackground": True,
        "preferCSSPageSize": False,
        "marginTop": 0.4, "marginBottom": 0.4,
        "marginLeft": 0.4, "marginRight": 0.4,
    })
    return resp.get("result", {}).get("data", "")


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="从用户浏览器抓取文章并保存")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="CDP 地址")
    parser.add_argument("--tab-url", default=None, help="匹配标签页 URL 的关键词")
    parser.add_argument("--output-dir", default=os.path.expanduser("~/Artical/Weixin"), help="保存目录")
    parser.add_argument("--format", choices=["md", "pdf", "both"], default="both", help="输出格式")
    parser.add_argument("--no-images", action="store_true", help="不下载图片")
    parser.add_argument("--no-scroll", action="store_true", help="不滚动触发懒加载")
    args = parser.parse_args()

    # 查找标签页
    print("▶ 查找标签页...")
    tab = find_tab(args.cdp_url, args.tab_url)
    if not tab:
        print("✘ 未找到匹配的标签页")
        sys.exit(1)
    print(f"  标签页: {tab['title']}")
    print(f"  URL: {tab['url']}")

    # 识别站点
    adapter = get_adapter(tab["url"])
    print(f"  站点类型: {adapter['name']}")

    # 连接
    cdp = CDPClient(tab["webSocketDebuggerUrl"])

    try:
        # 懒加载
        if not args.no_scroll and adapter.get("has_lazy_load"):
            print("\n▶ 滚动页面触发懒加载...")
            trigger_lazy_load(cdp)

        # 提取文章
        print("\n▶ 提取文章内容...")
        article = extract_article(cdp, adapter)
        print(f"  标题: {article['title']}")
        print(f"  作者: {article['author']}")
        print(f"  图片: {len(article['images'])} 张")

        # 准备目录
        fname = safe_filename(article["title"])
        os.makedirs(args.output_dir, exist_ok=True)
        img_dir = os.path.join(args.output_dir, "images")

        # 下载图片
        img_map = {}
        if not args.no_images and article["images"]:
            print(f"\n▶ 下载图片（{'防盗链模式' if adapter.get('anti_hotlink') else '直接下载'}）...")
            img_map = download_images(cdp, article["images"], img_dir)
            print(f"  共下载 {len(img_map)} 张有效图片")

        # 生成 Markdown
        if args.format in ("md", "both"):
            print("\n▶ 生成 Markdown...")
            md = generate_markdown(article, tab["url"], img_map, args.output_dir)
            md_path = os.path.join(args.output_dir, f"{fname}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"  ✔ {md_path} ({os.path.getsize(md_path)/1024:.1f}KB)")

        # 生成 PDF
        if args.format in ("pdf", "both"):
            print("\n▶ 生成 PDF...")
            pdf_data = generate_pdf(cdp, article.get("html", ""), img_map)
            if pdf_data:
                pdf_path = os.path.join(args.output_dir, f"{fname}.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(base64.b64decode(pdf_data))
                print(f"  ✔ {pdf_path} ({os.path.getsize(pdf_path)/1024/1024:.1f}MB)")
            else:
                print("  ✘ PDF 生成失败")

        # 输出 JSON 摘要（供 Agent 解析）
        summary = {
            "title": article["title"],
            "author": article["author"],
            "url": tab["url"],
            "images_count": len(img_map),
            "output_dir": args.output_dir,
        }
        print(f"\n✅ 完成！")
        print(f"RESULT_JSON:{json.dumps(summary, ensure_ascii=False)}")

    finally:
        cdp.close()


if __name__ == "__main__":
    main()
