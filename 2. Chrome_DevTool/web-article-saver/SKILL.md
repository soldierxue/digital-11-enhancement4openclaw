---
name: web-article-saver
description: >
  Save web articles (with images) from the user's browser to local files as Markdown and/or PDF.
  Handles anti-hotlinking sites like WeChat/微信公众号 by fetching images through the browser context.
  Activate when user asks to: save/grab/capture an article, save a webpage, download article content,
  保存文章, 抓取网页, 保存公众号文章, 把这篇文章存下来, save what's open in the browser,
  or any request involving capturing web content with images from the user's browser.
---

# Web Article Saver

Save web articles (including images) from the user's browser to local Markdown + PDF files.
Bypasses anti-hotlinking (e.g. WeChat/微信) by fetching images inside the browser context via CDP.

## Prerequisites

- User browser running with `--remote-debugging-port=9222 --remote-allow-origins=*`
- `websocket-client` Python package installed
- Supported sites: 微信公众号, 知乎专栏, any generic webpage

## Quick Use

```bash
python3 scripts/save_article.py --cdp-url http://127.0.0.1:9222 --output-dir ~/Artical/Weixin
```

## Workflow

1. Check user browser is running: `curl -s http://127.0.0.1:9222/json/list`
2. If not running, start it:
   ```bash
   DISPLAY=:1 nohup /snap/bin/chromium --remote-debugging-port=9222 --remote-allow-origins=* \
     --no-first-run --user-data-dir=$HOME/snap/chromium/common/user-profile &
   ```
3. List open tabs to find the article, or navigate to the URL the user provides
4. Run the script:
   ```bash
   python3 SKILL_DIR/scripts/save_article.py \
     --cdp-url http://127.0.0.1:9222 \
     --tab-url "mp.weixin.qq.com" \
     --output-dir ~/Artical/Weixin \
     --format both
   ```
5. Report results (title, image count, file paths) to the user

## Script Options

| Option | Default | Description |
|--------|---------|-------------|
| `--cdp-url` | `http://127.0.0.1:9222` | CDP address of user browser |
| `--tab-url` | (auto) | URL keyword to match a specific tab |
| `--output-dir` | `~/Artical/Weixin` | Save directory |
| `--format` | `both` | `md`, `pdf`, or `both` |
| `--no-images` | false | Skip image download |
| `--no-scroll` | false | Skip lazy-load scroll |

## Output Structure

```
output-dir/
├── 文章标题.md      # Markdown with local image references
├── 文章标题.pdf     # PDF with embedded images
└── images/          # Downloaded article images
    ├── img_00_xxxx.png
    ├── img_01_xxxx.jpg
    └── ...
```

## How Anti-Hotlink Bypass Works

Sites like WeChat check the HTTP `Referer` header. The script uses `Runtime.evaluate` to run
`fetch()` inside the browser page context — the browser sends the correct Referer automatically,
so image downloads succeed where direct `wget`/`curl` would fail.

## Supported Sites

| Site | Anti-hotlink | Lazy-load | Selectors |
|------|-------------|-----------|-----------|
| 微信公众号 | ✔ | ✔ | `#activity-name`, `#js_content` |
| 知乎专栏 | ✘ | ✔ | `.Post-Title`, `.Post-RichTextContainer` |
| 通用网页 | ✘ | ✘ | `article`, `main`, `body` fallback |

To add a new site, edit the `SITE_ADAPTERS` dict in `scripts/save_article.py`.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "未找到匹配的标签页" | Check `--tab-url` or open the article in the browser first |
| WebSocket 403 Forbidden | Restart browser with `--remote-allow-origins=*` |
| Images show as 1x1 placeholder | Use `--scroll` (default) to trigger lazy loading |
| PDF images blank | Script auto-embeds base64; if still blank, check console errors |
| "websocket-client not found" | `pip3 install --break-system-packages websocket-client` |
