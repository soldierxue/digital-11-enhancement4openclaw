#!/usr/bin/env python3
"""
cdp_client.py — CDP 客户端（复用 auto_session.py 模式）
连接 Chrome Remote Debugging，查找/操作标签页
"""

import json
import time
import subprocess
import sys

try:
    import websocket
except ImportError:
    print("ERROR: 需要 websocket-client。运行: pip3 install websocket-client")
    sys.exit(1)


CHANNELS_DOMAIN = "channels.weixin.qq.com"
CHANNELS_URL = "https://channels.weixin.qq.com/platform/post/create"


class CDPClient:
    """轻量 CDP 客户端"""

    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.msg_id = 0

    def send(self, method: str, params: dict = None) -> dict:
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self.msg_id:
                return resp

    def evaluate(self, expression: str, await_promise: bool = False):
        """执行 JS 表达式，返回结果值"""
        params = {"expression": expression, "returnByValue": True}
        if await_promise:
            params["awaitPromise"] = True
        resp = self.send("Runtime.evaluate", params)
        result = resp.get("result", {}).get("result", {})
        val = result.get("value")
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        return val

    def close(self):
        self.ws.close()


def list_tabs(cdp_url: str) -> list:
    """获取浏览器所有标签页"""
    try:
        result = subprocess.run(
            ["curl", "-s", f"{cdp_url}/json/list"],
            capture_output=True, text=True, timeout=5
        )
        return json.loads(result.stdout)
    except Exception as e:
        print(f"✗ 无法连接 CDP ({cdp_url}): {e}")
        return []


def find_channels_tab(cdp_url: str) -> dict | None:
    """查找视频号创作者中心标签页"""
    tabs = list_tabs(cdp_url)
    pages = [t for t in tabs if t.get("type") == "page"]

    for t in pages:
        if CHANNELS_DOMAIN in t.get("url", ""):
            return t
    return None


def navigate_to_channels(cdp_url: str) -> dict | None:
    """
    导航到视频号创作者中心。
    如果已有标签页则复用，否则在第一个标签页中导航。
    """
    tab = find_channels_tab(cdp_url)
    if tab:
        print(f"  ✓ 已找到视频号标签页: {tab.get('title', '')}")
        return tab

    print("  ⚠ 未找到视频号标签页，尝试导航...")
    tabs = list_tabs(cdp_url)
    pages = [t for t in tabs if t.get("type") == "page"]
    if not pages:
        print("  ✗ 浏览器中没有打开的页面")
        return None

    # 用第一个标签页导航
    target = pages[0]
    ws_url = target.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return None

    cdp = CDPClient(ws_url)
    try:
        cdp.send("Page.navigate", {"url": CHANNELS_URL})
        time.sleep(5)  # 等待页面加载
    finally:
        cdp.close()

    # 重新查找
    return find_channels_tab(cdp_url)


def connect_tab(tab: dict) -> CDPClient:
    """连接到指定标签页，返回 CDPClient"""
    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        raise RuntimeError("标签页无 WebSocket 调试地址")
    return CDPClient(ws_url)
