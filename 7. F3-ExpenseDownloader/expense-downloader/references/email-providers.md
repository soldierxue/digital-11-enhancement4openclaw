# 邮箱 Web 端 DOM 选择器参考

> 各邮箱的 DOM 结构差异大且经常变化。本文件提供基线选择器，
> 选择器失效时 Agent 应通过 `take_snapshot` 获取当前 DOM 动态调整。

---

## Gmail (mail.google.com)

### 搜索

```javascript
// 搜索框
const searchBox = document.querySelector("input[aria-label='Search mail']")
  || document.querySelector("input[aria-label='搜索邮件']");  // 中文界面

// 输入搜索词并触发搜索
searchBox.focus();
searchBox.value = "newer_than:90d (发票 OR invoice OR 水单)";
// 按 Enter 触发
searchBox.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', keyCode: 13, bubbles: true}));
```

### 邮件列表

```javascript
// 邮件行
const emailRows = document.querySelectorAll("tr.zA");

// 每行提取
emailRows.forEach(row => {
  const subject = row.querySelector(".bog span")?.textContent;
  const sender = row.querySelector(".yW span[email]")?.getAttribute("email");
  const senderName = row.querySelector(".yW span[email]")?.getAttribute("name");
  const date = row.querySelector(".xW span")?.getAttribute("title");
  const snippet = row.querySelector(".y2")?.textContent;
  const hasAttachment = !!row.querySelector(".yf img, .brd");
});
```

### 邮件详情

```javascript
// 打开邮件后
const subject = document.querySelector("h2.hP")?.textContent;
const body = document.querySelector(".a3s.aiL");  // 邮件正文容器

// 附件区域
const attachments = document.querySelectorAll(".aZo");  // 附件卡片
attachments.forEach(att => {
  const filename = att.querySelector(".aV3")?.textContent;
  const downloadBtn = att.querySelector("[data-tooltip='Download']")
    || att.querySelector("[aria-label='Download']");
  // downloadBtn.click() 触发下载
});
```

### 返回列表

```javascript
// 点击返回按钮
document.querySelector("[aria-label='Back to Inbox']")?.click()
  || document.querySelector("[aria-label='返回收件箱']")?.click();
```

### Gmail 搜索语法

Gmail 支持高级搜索运算符，可精确控制扫描范围：

```
newer_than:90d          # 最近 90 天
older_than:7d           # 7 天前
has:attachment           # 有附件
filename:pdf             # 附件名含 pdf
from:didifapiao@*        # 特定发件人
```

---

## 163 邮箱 (mail.163.com)

### ⚠️ 特殊注意: iframe 结构

163 邮箱使用多层 iframe 嵌套，操作前需注意：
- 搜索框通常在主文档顶部
- 邮件列表在 `iframe[id*='main']` 或 `iframe[id*='list']` 中
- 邮件正文可能在更深层的 `iframe[id*='reader']` 或 `iframe[id*='mail_body']` 中
- CDP 中可通过 `Page.getFrameTree` 获取 frame 层级，或直接在主文档中通过 `contentDocument` 访问

```javascript
// 获取主内容 iframe 的 document
const mainFrame = document.querySelector("iframe[id*='main']");
const doc = mainFrame?.contentDocument || document;
```

### 搜索

```javascript
// 搜索框（在主文档顶部）
const searchBox = document.querySelector("#search-key")
  || document.querySelector("input.nui-ipt-input")
  || document.querySelector("input[placeholder*='搜索']");

searchBox.focus();
// 使用 native setter 确保框架能感知值变化
const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value').set;
nativeInputValueSetter.call(searchBox, "发票 OR 水单 OR 收据");
searchBox.dispatchEvent(new Event('input', {bubbles: true}));

// 触发搜索
const searchBtn = document.querySelector("#search-btn")
  || document.querySelector(".nui-btn-hasIcon")
  || document.querySelector("a.js-component-search-btn");
if (searchBtn) searchBtn.click();
```

### 邮件列表

163 邮箱版本差异大，邮件行选择器需要多重兜底：

```javascript
// 在 mainFrame iframe 内操作
const mainFrame = document.querySelector("iframe[id*='main']");
const doc = mainFrame?.contentDocument || document;

// 邮件行（按优先级尝试）
let rows = doc.querySelectorAll("div[id^='divNet498']");   // 经典版
if (!rows.length) rows = doc.querySelectorAll(".nM0 .nM1"); // 新版
if (!rows.length) rows = doc.querySelectorAll("div.js-component-mailitem");
if (!rows.length) rows = doc.querySelectorAll("div[data-mrid]");
if (!rows.length) rows = doc.querySelectorAll("tr[oid]");   // 旧版表格布局

rows.forEach(row => {
  // 主题
  const subject = row.querySelector(".nM3")?.textContent
    || row.querySelector(".subjectText")?.textContent
    || row.querySelector("[title]")?.getAttribute("title")
    || row.querySelector("b")?.textContent;

  // 发件人
  const sender = row.querySelector(".nM2")?.textContent
    || row.querySelector(".sender")?.textContent
    || row.querySelector("[data-sender]")?.getAttribute("data-sender");

  // 日期
  const date = row.querySelector(".nM5")?.textContent
    || row.querySelector(".time")?.textContent
    || row.querySelector("[data-date]")?.getAttribute("data-date");

  // 附件标记
  const hasAttachment = !!(
    row.querySelector(".nM4 img")
    || row.querySelector(".icon-attachment")
    || row.querySelector("[class*='attach']")
  );
});
```

### 邮件详情

```javascript
// 在 mainFrame iframe 内
const doc = mainFrame?.contentDocument || document;

// 主题
const subject = doc.querySelector("h1.tit")?.textContent
  || doc.querySelector(".mailDetail h1")?.textContent;

// 邮件正文（通常在嵌套 iframe 中）
const bodyFrame = doc.querySelector("iframe[id*='reader']")
  || doc.querySelector("iframe[id*='mail_body']")
  || doc.querySelector("iframe.mailContent");
const bodyDoc = bodyFrame?.contentDocument;
const bodyText = bodyDoc?.body?.textContent || "";

// 附件
const attachments = doc.querySelectorAll(".ico_big, .js-component-attachment, .attachList li");
attachments.forEach(att => {
  const filename = att.querySelector(".name")?.textContent
    || att.querySelector("[title]")?.getAttribute("title");

  // 下载按钮/链接
  const downloadLink = att.querySelector("a[download]")
    || att.querySelector("a[href*='download']")
    || att.querySelector(".oper a:first-child");
  // downloadLink.click() 触发下载
});
```

### 返回列表

```javascript
// 返回按钮
const backBtn = doc.querySelector("a.js-component-back")
  || doc.querySelector("[class*='return']")
  || doc.querySelector("[class*='back']");
if (backBtn) backBtn.click();
```

### 163 邮箱搜索限制

163 邮箱搜索不支持 Gmail 那样的高级运算符（如 `newer_than:`），
搜索范围控制需要：
- 搜索后在页面上选择时间范围筛选器（如果有）
- 或者由 Agent 在提取结果后根据日期字段做二次过滤

---

## 通用策略

当以上适配器的选择器都失效时，Agent 应:

1. 使用 `take_snapshot` 获取当前页面 DOM 结构
2. 识别搜索框、邮件列表、邮件详情的 DOM 模式
3. 动态构造选择器
4. 将新发现的选择器记录下来，供后续使用

### 邮箱类型自动检测

```python
EMAIL_PROVIDERS = {
    "mail.google.com": "gmail",
    "mail.163.com": "163",
    "mail.126.com": "163",   # 126 邮箱与 163 同属网易，DOM 结构相似
}

def detect_provider(tab_url):
    for domain, provider in EMAIL_PROVIDERS.items():
        if domain in tab_url:
            return provider
    return "unknown"
```
