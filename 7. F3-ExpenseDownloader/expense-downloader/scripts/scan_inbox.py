#!/usr/bin/env python3
"""
scan_inbox.py — 扫描用户已登录的邮箱页面，提取邮件列表摘要。

通过 CDP 连接到用户浏览器中已打开的邮箱标签页，
利用邮箱搜索功能筛选近 N 个月的 Expense 相关邮件，
提取每封邮件的摘要信息输出为 JSON。

用法:
    python3 scan_inbox.py [选项]

选项:
    --cdp-url URL       CDP 地址 (默认: http://127.0.0.1:9222)
    --tab-url PATTERN   匹配邮箱标签页的关键词 (默认: 自动检测)
    --months N          扫描最近几个月 (默认: 3)
    --output PATH       输出 JSON 路径 (默认: /tmp/expense-scan-result.json)
    --provider TYPE     强制指定邮箱: gmail, 163 (默认: 自动检测)
"""

import json
import subprocess
import os
import sys
import time
import argparse
import re

try:
    import websocket
except ImportError:
    print("ERROR: 需要 websocket-client。运行: pip3 install --break-system-packages websocket-client")
    sys.exit(1)


# ============================================================
# 邮箱搜索关键词
# ============================================================

EXPENSE_KEYWORDS = (
    "发票 OR invoice OR 水单 OR folio OR 收据 OR receipt "
    "OR 账单 OR bill OR 行程单 OR 报销单"
)

NEGATIVE_KEYWORDS = [
    "退票", "退款", "还款提醒", "预订确认", "对账单", "周报", "月报",
    "unsubscribe", "广告", "促销", "优惠券", "积分", "会员",
    "密码", "验证码", "安全提醒", "登录", "注册",
]


# ============================================================
# 邮箱适配器（仅支持 Gmail 和 163 邮箱）
# ============================================================

EMAIL_ADAPTERS = {
    "gmail": {
        "name": "Gmail",
        "domains": ["mail.google.com"],
        "search_query_template": "newer_than:{days}d ({keywords})",
        # Phase 1: 在搜索框输入关键词并搜索
        "search_js": """
        (async () => {
            const searchBox = document.querySelector("input[aria-label='Search mail']")
                || document.querySelector("input[aria-label='搜索邮件']")
                || document.querySelector("input[name='q']");
            if (!searchBox) return JSON.stringify({error: "搜索框未找到"});

            searchBox.focus();
            searchBox.value = '';
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(searchBox, SEARCH_QUERY);
            searchBox.dispatchEvent(new Event('input', {bubbles: true}));

            await new Promise(r => setTimeout(r, 300));
            searchBox.dispatchEvent(new KeyboardEvent('keydown',
                {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
            searchBox.form?.submit?.();

            return JSON.stringify({ok: true});
        })()
        """,
        # Phase 2: 提取邮件列表
        "extract_js": """
        (() => {
            const rows = document.querySelectorAll("tr.zA");
            if (!rows.length) return JSON.stringify({emails: [], count: 0});

            const emails = [];
            rows.forEach((row, idx) => {
                const subjectEl = row.querySelector(".bog span") || row.querySelector(".bqe");
                const senderEl = row.querySelector(".yW span[email]");
                const dateEl = row.querySelector(".xW span");
                const snippetEl = row.querySelector(".y2");
                const hasAttach = !!(row.querySelector(".yf img") || row.querySelector(".brd"));

                emails.push({
                    index: idx,
                    subject: subjectEl?.textContent?.trim() || "",
                    sender: senderEl?.getAttribute("email") || "",
                    senderName: senderEl?.getAttribute("name") || senderEl?.textContent?.trim() || "",
                    date: dateEl?.getAttribute("title") || dateEl?.textContent?.trim() || "",
                    snippet: snippetEl?.textContent?.trim() || "",
                    hasAttachment: hasAttach,
                });
            });
            return JSON.stringify({emails, count: emails.length});
        })()
        """,
    },
    "163": {
        "name": "163邮箱",
        "domains": ["mail.163.com"],
        "search_query_template": "{keywords}",
        # 163 邮箱搜索 — 163 使用 iframe 结构，搜索框在顶部导航区域
        "search_js": """
        (async () => {
            // 163 邮箱搜索框可能在主文档或 iframe 中
            // 先尝试主文档中的搜索框
            let searchBox = document.querySelector("#search-key")
                || document.querySelector("input.nui-ipt-input")
                || document.querySelector("input[placeholder*='搜索']")
                || document.querySelector("input[placeholder*='search']");

            // 如果主文档没有，尝试在 iframe 中查找
            if (!searchBox) {
                const frames = document.querySelectorAll("iframe");
                for (const frame of frames) {
                    try {
                        const doc = frame.contentDocument;
                        if (doc) {
                            searchBox = doc.querySelector("#search-key")
                                || doc.querySelector("input.nui-ipt-input")
                                || doc.querySelector("input[placeholder*='搜索']");
                            if (searchBox) break;
                        }
                    } catch(e) { /* 跨域 iframe 忽略 */ }
                }
            }

            if (!searchBox) return JSON.stringify({error: "搜索框未找到，163邮箱 DOM 可能已变化"});

            searchBox.focus();
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(searchBox, SEARCH_QUERY);
            searchBox.dispatchEvent(new Event('input', {bubbles: true}));

            await new Promise(r => setTimeout(r, 500));

            // 尝试多种方式触发搜索
            const searchBtn = document.querySelector("#search-btn")
                || document.querySelector(".nui-btn-hasIcon")
                || document.querySelector("a.js-component-search-btn")
                || document.querySelector("span.nui-btn-text");
            if (searchBtn) {
                searchBtn.click();
            } else {
                searchBox.dispatchEvent(new KeyboardEvent('keydown',
                    {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
            }

            return JSON.stringify({ok: true});
        })()
        """,
        # 163 邮箱邮件列表提取 — 163 邮件列表在 iframe 中
        "extract_js": """
        (() => {
            // 163 邮箱的邮件列表通常在 iframe 中
            let doc = document;
            const mainFrame = document.querySelector("iframe[id*='main']")
                || document.querySelector("iframe[id*='list']");
            if (mainFrame) {
                try { doc = mainFrame.contentDocument || document; } catch(e) {}
            }

            // 尝试多种邮件行选择器（163 邮箱版本差异大）
            let rows = doc.querySelectorAll("div[id^='divNet498']");  // 经典版
            if (!rows.length) rows = doc.querySelectorAll(".nM0 .nM1");
            if (!rows.length) rows = doc.querySelectorAll("div.js-component-mailitem");
            if (!rows.length) rows = doc.querySelectorAll("div[data-mrid]");
            if (!rows.length) rows = doc.querySelectorAll("tr[oid]");  // 旧版表格布局
            if (!rows.length) rows = doc.querySelectorAll(".mail-list li, .mail-list .item");

            if (!rows.length) return JSON.stringify({emails: [], count: 0,
                hint: "未找到邮件行，Agent 可通过 take_snapshot 获取 DOM 结构"});

            const emails = [];
            rows.forEach((row, idx) => {
                // 主题 — 尝试多种选择器
                const subject = (
                    row.querySelector(".nM3")?.textContent
                    || row.querySelector(".subjectText")?.textContent
                    || row.querySelector("[title]")?.getAttribute("title")
                    || row.querySelector("b")?.textContent
                    || row.querySelector("span.subject")?.textContent
                    || ""
                ).trim();

                // 发件人
                const sender = (
                    row.querySelector(".nM2")?.textContent
                    || row.querySelector(".sender")?.textContent
                    || row.querySelector("[data-sender]")?.getAttribute("data-sender")
                    || ""
                ).trim();

                // 日期
                const date = (
                    row.querySelector(".nM5")?.textContent
                    || row.querySelector(".time")?.textContent
                    || row.querySelector("[data-date]")?.getAttribute("data-date")
                    || ""
                ).trim();

                // 附件标记
                const hasAttach = !!(
                    row.querySelector(".nM4 img")
                    || row.querySelector(".icon-attachment")
                    || row.querySelector("[class*='attach']")
                );

                if (subject) {
                    emails.push({
                        index: idx,
                        subject: subject,
                        sender: sender,
                        senderName: sender,
                        date: date,
                        snippet: "",
                        hasAttachment: hasAttach,
                    });
                }
            });
            return JSON.stringify({emails, count: emails.length});
        })()
        """,
    },
}


# ============================================================
# 邮箱类型检测
# ============================================================

def detect_provider(tab_url):
    """根据标签页 URL 检测邮箱类型"""
    for provider_id, adapter in EMAIL_ADAPTERS.items():
        for domain in adapter["domains"]:
            if domain in tab_url:
                return provider_id
    return None


# ============================================================
# CDP 通信（复用 web-article-saver 模式）
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


def find_email_tab(cdp_url, tab_url_pattern=None):
    """查找邮箱标签页"""
    result = subprocess.run(
        ["curl", "-s", f"{cdp_url}/json/list"],
        capture_output=True, text=True, timeout=5
    )
    tabs = json.loads(result.stdout)
    pages = [t for t in tabs if t.get("type") == "page"]

    if not pages:
        return None, None

    # 如果指定了 pattern，优先匹配
    if tab_url_pattern:
        for t in pages:
            if tab_url_pattern in t.get("url", ""):
                provider = detect_provider(t["url"])
                return t, provider

    # 自动检测邮箱标签页
    email_domains = []
    for adapter in EMAIL_ADAPTERS.values():
        email_domains.extend(adapter["domains"])

    for t in pages:
        url = t.get("url", "")
        for domain in email_domains:
            if domain in url:
                provider = detect_provider(url)
                return t, provider

    return None, None


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="扫描邮箱中的 Expense 相关邮件")
    parser.add_argument("--cdp-url", default=os.environ.get("EXPENSE_CDP_URL", "http://127.0.0.1:9222"),
                        help="CDP 地址")
    parser.add_argument("--tab-url", default=None, help="匹配邮箱标签页的关键词")
    parser.add_argument("--months", type=int,
                        default=int(os.environ.get("EXPENSE_MONTHS", "3")),
                        help="扫描最近几个月")
    parser.add_argument("--output", default="/tmp/expense-scan-result.json",
                        help="输出 JSON 路径")
    parser.add_argument("--provider", choices=["gmail", "163"],
                        default=None, help="强制指定邮箱类型: gmail, 163")
    args = parser.parse_args()

    # Step 1: 查找邮箱标签页
    print("▶ 查找邮箱标签页...")
    tab, auto_provider = find_email_tab(args.cdp_url, args.tab_url)
    if not tab:
        print("✘ 未找到邮箱标签页。请先在 Chrome 中打开并登录邮箱。")
        print("  支持: Gmail (mail.google.com), 163邮箱 (mail.163.com)")
        sys.exit(1)

    provider = args.provider or auto_provider
    if not provider:
        print(f"✘ 无法识别邮箱类型: {tab['url']}")
        print("  请使用 --provider 参数指定: gmail, 163")
        sys.exit(1)

    adapter = EMAIL_ADAPTERS[provider]
    print(f"  邮箱类型: {adapter['name']}")
    print(f"  标签页: {tab['title']}")
    print(f"  URL: {tab['url'][:80]}...")

    # Step 2: 连接 CDP
    print("\n▶ 连接浏览器...")
    cdp = CDPClient(tab["webSocketDebuggerUrl"])

    try:
        # Step 3: 构造搜索词并搜索
        days = args.months * 30
        search_query = adapter["search_query_template"].format(
            days=days, keywords=EXPENSE_KEYWORDS
        )
        print(f"\n▶ 搜索邮件: {search_query[:80]}...")

        search_js = adapter["search_js"].replace("SEARCH_QUERY", json.dumps(search_query))
        search_result = cdp.evaluate(search_js, await_promise=True)

        if search_result:
            parsed = json.loads(search_result) if isinstance(search_result, str) else search_result
            if parsed.get("error"):
                print(f"  ⚠️ 搜索失败: {parsed['error']}")
                print("  提示: 邮箱 DOM 结构可能已变化，Agent 可通过 take_snapshot 动态调整")
                sys.exit(1)

        # 等待搜索结果加载
        print("  等待搜索结果加载...")
        time.sleep(5)

        # Step 4: 提取邮件列表
        print("\n▶ 提取邮件列表...")
        extract_result = cdp.evaluate(adapter["extract_js"])

        if not extract_result:
            print("  ✘ 未能提取邮件列表")
            sys.exit(1)

        data = json.loads(extract_result) if isinstance(extract_result, str) else extract_result
        emails = data.get("emails", [])
        hint = data.get("hint", "")
        print(f"  找到 {len(emails)} 封邮件")
        if hint:
            print(f"  💡 {hint}")

        # Step 5: 基础过滤（排除明显非 Expense 邮件）
        filtered = []
        for email in emails:
            subject = email.get("subject", "")
            skip = False
            for neg in NEGATIVE_KEYWORDS:
                if neg in subject:
                    skip = True
                    break
            if not skip:
                filtered.append(email)

        print(f"  基础过滤后: {len(filtered)} 封")

        # Step 6: 输出结果
        output = {
            "provider": provider,
            "providerName": adapter["name"],
            "scanMonths": args.months,
            "searchQuery": search_query,
            "totalFound": len(emails),
            "afterFilter": len(filtered),
            "emails": filtered,
        }

        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 扫描完成！")
        print(f"  总邮件: {len(emails)}")
        print(f"  过滤后: {len(filtered)}")
        print(f"  输出: {args.output}")

        # 打印摘要供 Agent 快速浏览
        print(f"\n📧 邮件摘要:")
        for e in filtered[:20]:
            att_mark = "📎" if e.get("hasAttachment") else "  "
            print(f"  {att_mark} [{e['index']:2d}] {e['date'][:10]}  "
                  f"{e['sender'][:25]:25s}  {e['subject'][:50]}")

        if len(filtered) > 20:
            print(f"  ... 还有 {len(filtered) - 20} 封（详见 JSON 输出）")

        print(f"\nRESULT_JSON:{json.dumps({'output': args.output, 'count': len(filtered)}, ensure_ascii=False)}")

    finally:
        cdp.close()


if __name__ == "__main__":
    main()
