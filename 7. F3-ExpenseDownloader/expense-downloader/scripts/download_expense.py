#!/usr/bin/env python3
"""
download_expense.py — 从邮箱页面下载 Expense 材料（发票/水单/收据）。

通过 CDP 操作浏览器，逐封打开被标记的邮件，下载附件或提取链接下载。
支持 Gmail 和 163 邮箱。

用法:
    python3 download_expense.py [选项]

选项:
    --cdp-url URL           CDP 地址 (默认: http://127.0.0.1:9222)
    --email-indices LIST    要下载的邮件索引，逗号分隔 (如: "0,2,5,8")
    --output-dir DIR        下载目录 (默认: ~/Expenses/downloads)
    --scan-result PATH      scan_inbox.py 输出的 JSON
    --timeout SECS          单个下载超时秒数 (默认: 30)
"""

import json
import subprocess
import os
import sys
import time
import re
import base64
import zipfile
import io
import hashlib
import argparse
import shutil
import glob

try:
    import websocket
except ImportError:
    print("ERROR: 需要 websocket-client。运行: pip3 install --break-system-packages websocket-client")
    sys.exit(1)


# ============================================================
# CDP 通信
# ============================================================

class CDPClient:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60)
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
        return result.get("value")

    def close(self):
        self.ws.close()


def find_tab(cdp_url, tab_url_pattern=None):
    """查找邮箱标签页"""
    result = subprocess.run(
        ["curl", "-s", f"{cdp_url}/json/list"],
        capture_output=True, text=True, timeout=5
    )
    tabs = json.loads(result.stdout)
    pages = [t for t in tabs if t.get("type") == "page"]
    if not pages:
        return None

    email_domains = [
        "mail.google.com", "mail.163.com", "mail.126.com",
    ]

    if tab_url_pattern:
        for t in pages:
            if tab_url_pattern in t.get("url", ""):
                return t

    for t in pages:
        url = t.get("url", "")
        for domain in email_domains:
            if domain in url:
                return t
    return None


# ============================================================
# 发票平台 URL 模式
# ============================================================

INVOICE_URL_PATTERNS = [
    "baiwang.com", "fapiao.com", "xforceplus.com",
    "51fapiao", "einvoice", "invoice", "fapiao",
    "download", "pdf",
]


# ============================================================
# Gmail 特定操作
# ============================================================

GMAIL_CLICK_EMAIL_JS = """
(async () => {{
    const rows = document.querySelectorAll("tr.zA");
    const target = rows[{index}];
    if (!target) return JSON.stringify({{error: "邮件行未找到", index: {index}}});
    target.click();
    await new Promise(r => setTimeout(r, 2000));
    return JSON.stringify({{ok: true}});
}})()
"""

GMAIL_EXTRACT_DETAIL_JS = """
(() => {
    const subject = document.querySelector("h2.hP")?.textContent?.trim() || "";
    const body = document.querySelector(".a3s.aiL");
    const bodyHtml = body?.innerHTML || "";
    const bodyText = body?.textContent || "";

    // 提取附件
    const attachments = [];
    document.querySelectorAll(".aZo, .aQH").forEach((att, i) => {
        const name = att.querySelector(".aV3, .aQA span")?.textContent?.trim() || "";
        const isPdf = name.toLowerCase().endsWith(".pdf");
        const isZip = name.toLowerCase().endsWith(".zip");
        attachments.push({index: i, filename: name, isPdf, isZip});
    });

    // 提取链接（关键：取 display text 而非 href）
    const links = [];
    if (body) {
        body.querySelectorAll("a[href]").forEach(a => {
            const href = a.href || "";
            const displayText = a.textContent?.trim() || "";
            const textUrls = displayText.match(/https?:\\/\\/[^\\s<>"']+/g) || [];
            links.push({href, displayText, textUrls});
        });
    }

    // QR 码 base64 图片
    const qrImages = [];
    if (body) {
        body.querySelectorAll("img[src^='data:image']").forEach(img => {
            if (img.src.includes("base64")) qrImages.push(img.src);
        });
    }

    return JSON.stringify({
        subject, bodyText: bodyText.substring(0, 2000),
        attachments, links, qrImages: qrImages.length,
        hasAttachments: attachments.length > 0,
    });
})()
"""

GMAIL_DOWNLOAD_ATTACHMENT_JS = """
(async () => {{
    const attachments = document.querySelectorAll(".aZo, .aQH");
    const att = attachments[{att_index}];
    if (!att) return JSON.stringify({{error: "附件未找到"}});

    const downloadBtn = att.querySelector("[data-tooltip='Download']")
        || att.querySelector("[data-tooltip='下载']")
        || att.querySelector("[aria-label='Download']")
        || att.querySelector("[aria-label='下载']")
        || att.querySelector(".aQy");

    if (downloadBtn) {{
        downloadBtn.click();
        await new Promise(r => setTimeout(r, 1000));
        return JSON.stringify({{ok: true, method: "button"}});
    }}

    att.click();
    await new Promise(r => setTimeout(r, 1000));
    return JSON.stringify({{ok: true, method: "click"}});
}})()
"""

GMAIL_BACK_TO_LIST_JS = """
(async () => {
    const backBtn = document.querySelector("[aria-label='Back to Inbox']")
        || document.querySelector("[aria-label='返回收件箱']")
        || document.querySelector("[aria-label='Back to Search results']")
        || document.querySelector("[aria-label='返回搜索结果']")
        || document.querySelector(".lS .ak");
    if (backBtn) {
        backBtn.click();
        await new Promise(r => setTimeout(r, 1500));
        return JSON.stringify({ok: true});
    }
    history.back();
    await new Promise(r => setTimeout(r, 1500));
    return JSON.stringify({ok: true, method: "history.back"});
})()
"""


# ============================================================
# 163 邮箱特定操作
# ============================================================

NETEASE163_CLICK_EMAIL_JS = """
(async () => {{
    // 163 邮箱邮件列表可能在 iframe 中
    let doc = document;
    const mainFrame = document.querySelector("iframe[id*='main']")
        || document.querySelector("iframe[id*='list']");
    if (mainFrame) {{
        try {{ doc = mainFrame.contentDocument || document; }} catch(e) {{}}
    }}

    // 尝试多种邮件行选择器
    let rows = doc.querySelectorAll("div[id^='divNet498']");
    if (!rows.length) rows = doc.querySelectorAll(".nM0 .nM1");
    if (!rows.length) rows = doc.querySelectorAll("div.js-component-mailitem");
    if (!rows.length) rows = doc.querySelectorAll("div[data-mrid]");
    if (!rows.length) rows = doc.querySelectorAll("tr[oid]");

    const target = rows[{index}];
    if (!target) return JSON.stringify({{error: "邮件行未找到", index: {index}}});
    target.click();
    await new Promise(r => setTimeout(r, 2500));
    return JSON.stringify({{ok: true}});
}})()
"""

NETEASE163_EXTRACT_DETAIL_JS = """
(() => {
    // 163 邮箱邮件详情可能在 iframe 中
    let doc = document;
    const mainFrame = document.querySelector("iframe[id*='main']");
    if (mainFrame) {
        try { doc = mainFrame.contentDocument || document; } catch(e) {}
    }

    // 主题
    const subject = (
        doc.querySelector("h1.tit")?.textContent
        || doc.querySelector(".mailDetail h1")?.textContent
        || doc.querySelector("[class*='subject']")?.textContent
        || ""
    ).trim();

    // 邮件正文 — 163 邮件正文通常在嵌套 iframe 中
    let bodyText = "";
    let bodyHtml = "";
    const bodyFrame = doc.querySelector("iframe[id*='reader']")
        || doc.querySelector("iframe[id*='mail_body']")
        || doc.querySelector("iframe.mailContent");
    if (bodyFrame) {
        try {
            const bodyDoc = bodyFrame.contentDocument;
            bodyText = bodyDoc?.body?.textContent?.substring(0, 2000) || "";
            bodyHtml = bodyDoc?.body?.innerHTML || "";
        } catch(e) {}
    }
    if (!bodyText) {
        const bodyEl = doc.querySelector(".mailContent")
            || doc.querySelector("#mail_body")
            || doc.querySelector("[class*='mailbody']");
        bodyText = bodyEl?.textContent?.substring(0, 2000) || "";
        bodyHtml = bodyEl?.innerHTML || "";
    }

    // 附件
    const attachments = [];
    const attContainer = doc.querySelectorAll(".ico_big, .js-component-attachment, [class*='attach'] li, .attachList li");
    attContainer.forEach((att, i) => {
        const name = (
            att.querySelector(".name")?.textContent
            || att.querySelector("[title]")?.getAttribute("title")
            || att.querySelector("span")?.textContent
            || ""
        ).trim();
        const isPdf = name.toLowerCase().endsWith(".pdf");
        const isZip = name.toLowerCase().endsWith(".zip");
        attachments.push({index: i, filename: name, isPdf, isZip});
    });

    // 提取链接（取 display text 而非 href）
    const links = [];
    const bodyContainer = bodyFrame
        ? (bodyFrame.contentDocument?.body || null)
        : (doc.querySelector(".mailContent") || doc.querySelector("#mail_body"));
    if (bodyContainer) {
        bodyContainer.querySelectorAll("a[href]").forEach(a => {
            const href = a.href || "";
            const displayText = a.textContent?.trim() || "";
            const textUrls = displayText.match(/https?:\\/\\/[^\\s<>"']+/g) || [];
            links.push({href, displayText, textUrls});
        });
    }

    return JSON.stringify({
        subject, bodyText,
        attachments, links, qrImages: 0,
        hasAttachments: attachments.length > 0,
    });
})()
"""

NETEASE163_DOWNLOAD_ATTACHMENT_JS = """
(async () => {{
    let doc = document;
    const mainFrame = document.querySelector("iframe[id*='main']");
    if (mainFrame) {{
        try {{ doc = mainFrame.contentDocument || document; }} catch(e) {{}}
    }}

    const attList = doc.querySelectorAll(".ico_big, .js-component-attachment, [class*='attach'] li, .attachList li");
    const att = attList[{att_index}];
    if (!att) return JSON.stringify({{error: "附件未找到"}});

    // 尝试找下载链接/按钮
    const downloadLink = att.querySelector("a[download]")
        || att.querySelector("a[href*='download']")
        || att.querySelector(".oper a:first-child")
        || att.querySelector("[class*='download']");

    if (downloadLink) {{
        downloadLink.click();
        await new Promise(r => setTimeout(r, 1500));
        return JSON.stringify({{ok: true, method: "link"}});
    }}

    // 兜底：点击附件名称（某些版本会弹出预览/下载选项）
    const nameEl = att.querySelector(".name") || att.querySelector("span");
    if (nameEl) {{
        nameEl.click();
        await new Promise(r => setTimeout(r, 1500));
        // 检查是否弹出了下载选项
        const dlBtn = doc.querySelector("[class*='download']")
            || doc.querySelector("a[download]");
        if (dlBtn) dlBtn.click();
        return JSON.stringify({{ok: true, method: "name_click"}});
    }}

    return JSON.stringify({{error: "未找到下载按钮"}});
}})()
"""

NETEASE163_BACK_TO_LIST_JS = """
(async () => {
    let doc = document;
    const mainFrame = document.querySelector("iframe[id*='main']");
    if (mainFrame) {
        try { doc = mainFrame.contentDocument || document; } catch(e) {}
    }

    // 163 邮箱返回列表按钮
    const backBtn = doc.querySelector("a.js-component-back")
        || doc.querySelector("[class*='return']")
        || doc.querySelector("[class*='back']")
        || doc.querySelector(".nui-toolbar a:first-child");

    if (backBtn) {
        backBtn.click();
        await new Promise(r => setTimeout(r, 2000));
        return JSON.stringify({ok: true});
    }

    // 兜底：浏览器后退
    history.back();
    await new Promise(r => setTimeout(r, 2000));
    return JSON.stringify({ok: true, method: "history.back"});
})()
"""


# ============================================================
# 链接分析
# ============================================================

def extract_invoice_urls(links_data):
    """从邮件链接数据中提取可能的发票下载 URL"""
    urls = []

    for link in links_data:
        # 优先取 display text 中的 URL（不会过期）
        for text_url in link.get("textUrls", []):
            for pattern in INVOICE_URL_PATTERNS:
                if pattern in text_url.lower():
                    urls.append({"url": text_url, "source": "displayText", "pattern": pattern})
                    break

        # 其次取 href（可能是追踪链接，但有些是直接链接）
        href = link.get("href", "")
        if href:
            for pattern in INVOICE_URL_PATTERNS:
                if pattern in href.lower():
                    tracking_domains = ["sendcloud", "mailchimp", "campaign-archive",
                                        "click.", "track.", "redirect."]
                    is_tracking = any(td in href.lower() for td in tracking_domains)
                    if not is_tracking:
                        urls.append({"url": href, "source": "href", "pattern": pattern})
                        break

    return urls


# ============================================================
# 文件工具
# ============================================================

def safe_filename(name):
    """生成安全文件名"""
    return re.sub(r'[<>:"/\\|?*\n\r]', '_', name).strip()[:200]


def make_unique_path(output_dir, filename):
    """生成唯一文件路径（重名加序号）"""
    path = os.path.join(output_dir, filename)
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(filename)
    n = 1
    while True:
        new_path = os.path.join(output_dir, f"{base} ({n}){ext}")
        if not os.path.exists(new_path):
            return new_path
        n += 1


def process_zip(zip_path, output_dir):
    """解压 ZIP，提取 PDF 文件"""
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for name in z.namelist():
                if name.lower().endswith(".pdf"):
                    content = z.read(name)
                    fname = safe_filename(os.path.basename(name))
                    path = make_unique_path(output_dir, fname)
                    with open(path, "wb") as f:
                        f.write(content)
                    extracted.append(path)
                    print(f"    ✅ 从 ZIP 提取: {os.path.basename(path)} ({len(content)}B)")
    except zipfile.BadZipFile:
        print(f"    ⚠️ ZIP 文件损坏: {zip_path}")
    return extracted


def wait_for_download(download_dir, timeout=30, before_files=None):
    """等待新文件出现在下载目录中"""
    if before_files is None:
        before_files = set()

    start = time.time()
    while time.time() - start < timeout:
        current_files = set(glob.glob(os.path.join(download_dir, "*")))
        new_files = current_files - before_files

        completed = [f for f in new_files
                     if not f.endswith(".crdownload")
                     and not f.endswith(".tmp")
                     and not f.endswith(".part")]

        if completed:
            return completed

        time.sleep(1)

    return []


# ============================================================
# 通用下载流程（Gmail / 163 共用逻辑）
# ============================================================

def download_email(cdp, provider, idx, email_info, output_dir, timeout, before_files):
    """对单封邮件执行下载流程，返回 (downloaded_files, failure_info)"""
    subject = email_info.get("subject", "(无主题)")
    sender = email_info.get("sender", "")
    downloaded = []
    failure = None

    print(f"\n📧 [{idx}] {subject[:60]}")
    print(f"   From: {sender[:40]} | Date: {email_info.get('date', '')[:15]}")

    # 选择对应的 JS 模板
    if provider == "gmail":
        click_js = GMAIL_CLICK_EMAIL_JS.format(index=idx)
        extract_js = GMAIL_EXTRACT_DETAIL_JS
        download_att_js_tpl = GMAIL_DOWNLOAD_ATTACHMENT_JS
        back_js = GMAIL_BACK_TO_LIST_JS
    elif provider == "163":
        click_js = NETEASE163_CLICK_EMAIL_JS.format(index=idx)
        extract_js = NETEASE163_EXTRACT_DETAIL_JS
        download_att_js_tpl = NETEASE163_DOWNLOAD_ATTACHMENT_JS
        back_js = NETEASE163_BACK_TO_LIST_JS
    else:
        print(f"   ⚠️ 不支持的邮箱类型: {provider}")
        return [], {"index": idx, "subject": subject, "reason": f"{provider} not supported"}

    # Step 1: 点击打开邮件
    click_result = cdp.evaluate(click_js, await_promise=True)
    if click_result:
        parsed = json.loads(click_result) if isinstance(click_result, str) else click_result
        if parsed.get("error"):
            print(f"   ⚠️ 打开邮件失败: {parsed['error']}")
            return [], {"index": idx, "subject": subject, "reason": "click failed"}

    time.sleep(2)

    # Step 2: 提取邮件详情
    detail_result = cdp.evaluate(extract_js)
    if not detail_result:
        print(f"   ⚠️ 提取详情失败")
        cdp.evaluate(back_js, await_promise=True)
        return [], {"index": idx, "subject": subject, "reason": "extract failed"}

    detail = json.loads(detail_result) if isinstance(detail_result, str) else detail_result
    attachments = detail.get("attachments", [])
    links = detail.get("links", [])

    # Step 3: 决策树 — 下载
    if attachments:
        pdf_atts = [a for a in attachments if a.get("isPdf")]
        zip_atts = [a for a in attachments if a.get("isZip")]
        target_atts = pdf_atts or zip_atts or attachments[:1]

        for att in target_atts:
            att_idx = att["index"]
            fname = att.get("filename", f"attachment_{att_idx}")
            print(f"   📎 下载附件: {fname}")

            dl_js = download_att_js_tpl.format(att_index=att_idx)
            cdp.evaluate(dl_js, await_promise=True)

            new_files = wait_for_download(output_dir, timeout, before_files)
            if new_files:
                for nf in new_files:
                    print(f"   ✅ {os.path.basename(nf)} ({os.path.getsize(nf)}B)")
                    if nf.lower().endswith(".zip"):
                        extracted = process_zip(nf, output_dir)
                        downloaded.extend(extracted)
                        os.remove(nf)
                    else:
                        downloaded.append(nf)
                    before_files.add(nf)
            else:
                print(f"   ⚠️ 下载超时或未检测到新文件")
                failure = {"index": idx, "subject": subject,
                           "reason": "download timeout", "attachment": fname}
    else:
        # 无附件 → 提取链接
        invoice_urls = extract_invoice_urls(links)
        if invoice_urls:
            print(f"   🔗 找到 {len(invoice_urls)} 个可能的发票链接")
            link_success = False
            for url_info in invoice_urls[:3]:
                url = url_info["url"]
                print(f"      尝试: {url[:70]}...")

                new_tab_resp = cdp.send("Target.createTarget", {"url": url})
                target_id = new_tab_resp.get("result", {}).get("targetId")

                if target_id:
                    time.sleep(3)
                    new_files = wait_for_download(output_dir, timeout, before_files)
                    if new_files:
                        for nf in new_files:
                            print(f"   ✅ {os.path.basename(nf)} (from link)")
                            downloaded.append(nf)
                            before_files.add(nf)
                        cdp.send("Target.closeTarget", {"targetId": target_id})
                        link_success = True
                        break
                    else:
                        cdp.send("Target.closeTarget", {"targetId": target_id})

            if not link_success:
                print(f"   ⚠️ 所有链接均未成功下载")
                failure = {"index": idx, "subject": subject,
                           "reason": "links expired or invalid",
                           "urls": [u["url"][:80] for u in invoice_urls[:3]]}
        else:
            print(f"   ⚠️ 无附件且未找到发票链接")
            failure = {"index": idx, "subject": subject,
                       "reason": "no attachments or invoice links"}

    # Step 4: 返回邮件列表
    cdp.evaluate(back_js, await_promise=True)
    time.sleep(1)

    return downloaded, failure


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="从邮箱下载 Expense 材料")
    parser.add_argument("--cdp-url", default=os.environ.get("EXPENSE_CDP_URL", "http://127.0.0.1:9222"),
                        help="CDP 地址")
    parser.add_argument("--email-indices", required=True,
                        help="要下载的邮件索引，逗号分隔")
    parser.add_argument("--output-dir",
                        default=os.path.expanduser(os.environ.get("EXPENSE_OUTPUT_DIR", "~/Expenses/downloads")),
                        help="下载目录")
    parser.add_argument("--scan-result", required=True,
                        help="scan_inbox.py 输出的 JSON")
    parser.add_argument("--timeout", type=int, default=30,
                        help="单个下载超时秒数")
    args = parser.parse_args()

    # 解析邮件索引
    indices = [int(i.strip()) for i in args.email_indices.split(",") if i.strip()]
    if not indices:
        print("✘ 未指定邮件索引")
        sys.exit(1)

    # 读取扫描结果
    with open(args.scan_result, "r", encoding="utf-8") as f:
        scan_data = json.load(f)

    provider = scan_data.get("provider", "gmail")
    emails = scan_data.get("emails", [])
    print(f"▶ 邮箱类型: {scan_data.get('providerName', provider)}")
    print(f"  待下载: {len(indices)} 封邮件")

    # 准备下载目录
    os.makedirs(args.output_dir, exist_ok=True)

    # 查找邮箱标签页
    tab = find_tab(args.cdp_url)
    if not tab:
        print("✘ 未找到邮箱标签页")
        sys.exit(1)

    cdp = CDPClient(tab["webSocketDebuggerUrl"])

    # 设置下载行为
    cdp.send("Browser.setDownloadBehavior", {
        "behavior": "allowAndName",
        "downloadPath": args.output_dir,
        "eventsEnabled": True,
    })

    all_downloaded = []
    all_failed = []

    try:
        for idx in indices:
            email_info = None
            for e in emails:
                if e.get("index") == idx:
                    email_info = e
                    break

            if not email_info:
                print(f"\n⚠️ 索引 {idx} 未找到对应邮件，跳过")
                all_failed.append({"index": idx, "reason": "not found in scan result"})
                continue

            before_files = set(glob.glob(os.path.join(args.output_dir, "*")))
            dl_files, failure = download_email(
                cdp, provider, idx, email_info, args.output_dir, args.timeout, before_files
            )
            all_downloaded.extend(dl_files)
            if failure:
                all_failed.append(failure)

    finally:
        cdp.close()

    # 输出汇总
    print(f"\n{'='*60}")
    print(f"✅ 下载完成: {len(all_downloaded)} 个文件")
    for f_path in all_downloaded:
        size = os.path.getsize(f_path)
        print(f"   📄 {os.path.basename(f_path)} ({size/1024:.1f}KB)")

    if all_failed:
        print(f"\n⚠️ 失败: {len(all_failed)} 封邮件")
        for f_item in all_failed:
            print(f"   - [{f_item.get('index')}] {f_item.get('subject', '?')[:40]}: "
                  f"{f_item.get('reason', 'unknown')}")

    # 输出 JSON 结果
    result = {
        "downloaded": [{"path": p, "filename": os.path.basename(p),
                        "size": os.path.getsize(p)} for p in all_downloaded],
        "failed": all_failed,
        "outputDir": args.output_dir,
        "totalDownloaded": len(all_downloaded),
        "totalFailed": len(all_failed),
    }

    result_path = os.path.join(args.output_dir, "download-result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nRESULT_JSON:{json.dumps({'downloaded': len(all_downloaded), 'failed': len(all_failed), 'resultFile': result_path}, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
