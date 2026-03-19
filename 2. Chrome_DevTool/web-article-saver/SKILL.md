---
name: web-article-saver
description: >
  Save web articles (with images) to local Markdown and/or PDF files.
  Dual-engine: uses Scrapling (HTTP) as primary, falls back to CDP (browser context) for anti-hotlink sites.
  Activate when user asks to: save/grab/capture an article, save a webpage, download article content,
  保存文章, 抓取网页, 保存公众号文章, 把这篇文章存下来, save what's open in the browser,
  抓取这个链接, or any request involving capturing web content with images.
---

# Web Article Saver

Save web articles (including images) to local Markdown + PDF files.

**Dual-engine architecture:**
1. **Scrapling 引擎（优先）** — 通过 HTTP 直接抓取，无需浏览器，轻量高效
2. **CDP 引擎（回退）** — 通过浏览器上下文抓取，绕过防盗链（如微信公众号）

## Prerequisites

- `scrapling` Python package installed (primary engine)
- `websocket-client` Python package installed (CDP fallback)
- For CDP engine: browser running with `--remote-debugging-port=9222 --remote-allow-origins=*`

## Engine Selection Logic

| Site | Engine | Reason |
|------|--------|--------|
| mp.weixin.qq.com | CDP | Image anti-hotlink requires browser context |
| Other sites | Scrapling | Lightweight HTTP fetch, no browser needed |
| Scrapling blocked | CDP fallback | Use real browser session to bypass |

## Quick Use

```bash
# Scrapling engine (default, no browser needed)
python3 scripts/save_article.py --url "https://example.com/article" --output-dir ~/Artical

# CDP engine (for WeChat or when Scrapling fails)
python3 scripts/save_article.py --engine cdp --cdp-url http://127.0.0.1:9222 --tab-url "mp.weixin.qq.com"

# Scrapling CLI shortcut (extract to Markdown directly)
scrapling extract get 'https://example.com/article' output.md
```

## Workflow

1. Determine the target URL and site type
2. If WeChat (mp.weixin.qq.com) → use CDP engine:
   a. Check browser is running: `curl -s http://127.0.0.1:9222/json/list`
   b. Find the tab with the article open
   c. Run script with `--engine cdp`
3. If other site → use Scrapling engine:
   a. Run script with `--url <URL>` (Scrapling fetches via HTTP)
   b. If Scrapling fails (anti-bot, JS-rendered), retry with `--engine cdp`
4. Report results (title, image count, file paths) to the user

## Script Options

| Option | Default | Description |
|--------|---------|-------------|
| `--engine` | `auto` | Engine: `auto`, `scrapling`, `cdp` |
| `--url` | — | Target URL (Scrapling engine) |
| `--cdp-url` | `http://127.0.0.1:9222` | CDP address (CDP engine) |
| `--tab-url` | (auto) | URL keyword to match tab (CDP engine) |
| `--output-dir` | `~/Artical/Weixin` | Save directory |
| `--format` | `both` | `md`, `pdf`, or `both` |
| `--no-images` | false | Skip image download |
| `--no-scroll` | false | Skip lazy-load scroll (CDP engine) |
| `--stealthy` | false | Use StealthyFetcher (needs `scrapling[fetchers]`) |

## Output Structure

```
output-dir/
├── 文章标题.md      # Markdown with local image references
├── 文章标题.pdf     # PDF with embedded images (CDP engine only)
└── images/          # Downloaded article images
    ├── img_00_xxxx.png
    └── ...
```

## How It Works

### Scrapling Engine
Uses `Fetcher.get(url, stealthy_headers=True)` to fetch the page via HTTP, then extracts
content using CSS selectors. Images are downloaded directly via HTTP requests.
No browser needed — fast and lightweight.

### CDP Engine (Anti-Hotlink Bypass)
Sites like WeChat check the HTTP `Referer` header. The script uses `Runtime.evaluate` to run
`fetch()` inside the browser page context — the browser sends the correct Referer automatically,
so image downloads succeed where direct HTTP requests would fail.

## Supported Sites

| Site | Engine | Anti-hotlink | Lazy-load | Selectors |
|------|--------|-------------|-----------|-----------|
| 微信公众号 | CDP | ✔ | ✔ | `#activity-name`, `#js_content` |
| 知乎专栏 | Scrapling | ✘ | ✔ | `.Post-Title`, `.Post-RichTextContainer` |
| 通用网页 | Scrapling | ✘ | ✘ | `article`, `main`, `body` fallback |

To add a new site, edit the `SITE_ADAPTERS` dict in `scripts/save_article.py`.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "scrapling not found" | `pip3 install --break-system-packages scrapling` |
| Scrapling 被反爬拦截 | 加 `--stealthy` 或回退 `--engine cdp` |
| "未找到匹配的标签页" (CDP) | Check `--tab-url` or open the article in the browser first |
| WebSocket 403 Forbidden (CDP) | Restart browser with `--remote-allow-origins=*` |
| Images show as 1x1 placeholder | Use `--scroll` (default) to trigger lazy loading (CDP) |
| PDF images blank | Script auto-embeds base64; if still blank, check console errors |
| "websocket-client not found" | `pip3 install --break-system-packages websocket-client` |
