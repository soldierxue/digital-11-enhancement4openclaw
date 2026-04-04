#!/usr/bin/env python3
"""
auto_session.py — 通过 Chrome DevTools Protocol (CDP) 自动提取微信后台 cookie + token

连接到用户浏览器中已登录的微信公众号后台页面 (mp.weixin.qq.com)，
通过 Runtime.evaluate 提取 document.cookie 和 URL 中的 token 参数，
保存到 weixin_admin_session.json。

前置条件:
  - Chrome/Chromium 已启动并启用 Remote Debugging (--remote-debugging-port=9222)
  - 用户已在浏览器中登录 mp.weixin.qq.com 后台

用法:
  python3 auto_session.py                          # 默认 CDP 端口 9222
  python3 auto_session.py --cdp-url http://127.0.0.1:18800  # ARM64 Snap 端口
"""

import json
import subprocess
import os
import sys
import argparse

try:
    import websocket
except ImportError:
    print("ERROR: 需要 websocket-client。运行: pip3 install --break-system-packages websocket-client")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(SCRIPT_DIR, "weixin_admin_session.json")

WEIXIN_ADMIN_DOMAIN = "mp.weixin.qq.com"


# ── CDP 客户端 ────────────────────────────────────────────


class CDPClient:
    """轻量 CDP 客户端（复用 F3 scan_inbox.py 模式）"""

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

    def evaluate(self, expression, await_promise=False):
        params = {"expression": expression, "returnByValue": True}
        if await_promise:
            params["awaitPromise"] = True
        resp = self.send("Runtime.evaluate", params)
        result = resp.get("result", {}).get("result", {})
        if result.get("type") == "string":
            return result.get("value")
        return result.get("value")

    def close(self):
        self.ws.close()


# ── 查找微信后台标签页 ───────────────────────────────────


def find_weixin_admin_tab(cdp_url):
    """
    在浏览器中查找 mp.weixin.qq.com 标签页
    返回: tab dict 或 None
    """
    try:
        result = subprocess.run(
            ["curl", "-s", f"{cdp_url}/json/list"],
            capture_output=True, text=True, timeout=5
        )
        tabs = json.loads(result.stdout)
    except Exception as e:
        print(f"✗ 无法连接 CDP ({cdp_url}): {e}")
        print("  请确认浏览器已启动并启用 Remote Debugging:")
        print("  - headed 模式: --remote-debugging-port=9222 --remote-allow-origins=*")
        print("  - ARM64 Snap: systemctl --user start chromium-headless (端口 18800)")
        return None

    pages = [t for t in tabs if t.get("type") == "page"]
    if not pages:
        print("✗ 浏览器中没有打开的页面")
        return None

    # 查找微信后台页面
    for t in pages:
        url = t.get("url", "")
        if WEIXIN_ADMIN_DOMAIN in url:
            return t

    print(f"✗ 未找到微信公众号后台页面 ({WEIXIN_ADMIN_DOMAIN})")
    print("  请先在浏览器中登录 https://mp.weixin.qq.com")
    print(f"\n  当前打开的页面:")
    for t in pages[:5]:
        print(f"    - {t.get('title', '(无标题)')}: {t.get('url', '')[:80]}")
    return None


# ── 提取 cookie + token ──────────────────────────────────


def extract_session(cdp_url):
    """
    通过 CDP 从微信后台页面提取 cookie + token
    返回: {"cookie": "...", "token": "..."} 或 None
    """
    tab = find_weixin_admin_tab(cdp_url)
    if not tab:
        return None

    print(f"  标签页: {tab.get('title', '')}")
    print(f"  URL: {tab.get('url', '')[:80]}...")

    # 连接 CDP
    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        print("✗ 标签页无 WebSocket 调试地址")
        return None

    print("\n▶ 连接浏览器...")
    cdp = CDPClient(ws_url)

    try:
        # 提取 cookie
        print("▶ 提取 cookie...")
        cookie = cdp.evaluate("document.cookie")
        if not cookie:
            print("✗ 无法获取 cookie，可能未登录或 session 已过期")
            print("  请在浏览器中重新登录 mp.weixin.qq.com")
            return None

        # 提取 token — 从 URL 参数或页面全局变量中获取
        print("▶ 提取 token...")
        token_js = """
        (() => {
            // 方法 1: 从当前 URL 参数中提取
            const urlParams = new URLSearchParams(window.location.search);
            let token = urlParams.get('token');
            if (token) return JSON.stringify({token: token, source: 'url'});

            // 方法 2: 从页面中的链接提取（后台页面的导航链接通常包含 token）
            const links = document.querySelectorAll('a[href*="token="]');
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const match = href.match(/token=(\\d+)/);
                if (match) return JSON.stringify({token: match[1], source: 'link'});
            }

            // 方法 3: 从页面 script 中提取（微信后台会在全局变量中存储 token）
            const scripts = document.querySelectorAll('script');
            for (const script of scripts) {
                const text = script.textContent || '';
                const match = text.match(/token['"\\s]*[:=]['"\\s]*(\\d{6,})/);
                if (match) return JSON.stringify({token: match[1], source: 'script'});
            }

            // 方法 4: 从 window.wx 或其他全局对象中提取
            if (window.wx && window.wx.commonData && window.wx.commonData.token) {
                return JSON.stringify({token: String(window.wx.commonData.token), source: 'wx.commonData'});
            }

            return JSON.stringify({token: null, source: 'not_found'});
        })()
        """
        token_result = cdp.evaluate(token_js)

        token = None
        if token_result:
            parsed = json.loads(token_result) if isinstance(token_result, str) else token_result
            token = parsed.get("token")
            source = parsed.get("source", "unknown")
            if token:
                print(f"  ✓ token 来源: {source}")

        if not token:
            print("⚠ 未能自动提取 token")
            print("  可能原因: 当前页面 URL 中没有 token 参数")
            print("  建议: 在浏览器中点击「内容与互动」→「图文消息」，然后重试")
            print("  或者手动输入 token:")
            # 非交互模式下返回仅有 cookie 的结果
            if not sys.stdin.isatty():
                print("  (非交互模式，跳过手动输入)")
                return None
            manual_token = input("  Token (留空取消): ").strip()
            if not manual_token:
                return None
            token = manual_token

        return {"cookie": cookie, "token": token}

    finally:
        cdp.close()


# ── 保存 session ──────────────────────────────────────────


def save_session(session_data, output_path=None):
    """保存 session 到 JSON 文件"""
    path = output_path or SESSION_PATH
    session_data["note"] = "通过 CDP 自动提取，cookie 有效期约 2 小时，过期需重新提取"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Session 已保存到 {path}")
    print(f"  cookie 长度: {len(session_data.get('cookie', ''))} 字符")
    print(f"  token: {session_data.get('token', '')}")


# ── 主入口 ────────────────────────────────────────────────


def auto_extract_session(cdp_url="http://127.0.0.1:9222", output_path=None):
    """
    自动提取微信后台 session（供其他模块调用）
    返回: {"cookie": "...", "token": "..."} 或 None
    """
    print("▶ 自动提取微信后台 Session (CDP)...\n")

    session = extract_session(cdp_url)
    if not session:
        return None

    save_session(session, output_path)
    return session


def main():
    parser = argparse.ArgumentParser(
        description="通过 CDP 自动提取微信后台 cookie + token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
前置条件:
  1. Chrome/Chromium 已启用 Remote Debugging
  2. 用户已在浏览器中登录 mp.weixin.qq.com

示例:
  python3 auto_session.py                                    # 默认端口 9222
  python3 auto_session.py --cdp-url http://127.0.0.1:18800   # ARM64 Snap 端口
        """
    )
    parser.add_argument("--cdp-url",
                        default=os.environ.get("CDP_URL", "http://127.0.0.1:9222"),
                        help="CDP 地址 (默认: http://127.0.0.1:9222)")
    parser.add_argument("--output", default=None,
                        help=f"输出路径 (默认: {SESSION_PATH})")
    args = parser.parse_args()

    result = auto_extract_session(cdp_url=args.cdp_url, output_path=args.output)
    if not result:
        sys.exit(1)

    print("\n✅ 完成！现在可以运行 sync_articles.py 同步全量文章索引")


if __name__ == "__main__":
    main()
