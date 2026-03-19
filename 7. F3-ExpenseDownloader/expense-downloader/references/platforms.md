# 中国发票平台下载模式（浏览器自动化版）

> 本文档描述各发票平台的邮件特征和浏览器内下载方法。
> 与 Gmail API 版不同，所有操作通过 CDP 在浏览器中完成。

---

## 百望云 (Baiwang)

**发件人:** `*@baiwang.com`, `*@vip.baiwang.com`, `fapiao@yun.baiwang.com`

**邮件特征:** 邮件正文包含短链接（如 `http://u.baiwang.com/XXXXX`），指向 Vue SPA 预览页。

**⚠️ 关键经验:** 邮件中 `<a>` 标签的 `href` 是营销追踪链接（会过期），真实 URL 在标签的 display text 中：
```html
<a href="https://tracking.sendcloud.net/click/...">
  http://u.baiwang.com/XXXXX    ← 提取这个
</a>
```

**浏览器下载流程:**
1. 在邮件正文中提取真实 URL（从 `<a>` display text）
2. 在新标签页打开该 URL
3. 页面会重定向到预览页，URL 中包含 `param=` 参数
4. 找到下载按钮并点击，或直接构造下载 URL:
   ```
   https://pis.baiwang.com/bwmg/mix/bw/downloadFormat?param={PARAM}&formatType=pdf
   ```
5. 下载完成后关闭标签页

**下载按钮 JS 源码（参考）:**
```javascript
// Vue method: downloadInvoice
function(type) {
  location.href = location.origin + "/bwmg/mix/bw/downloadFormat?param=" + this.param + "&formatType=" + type
}
// type: "pdf", "ofd", "xml"
```

**格式:** `pdf`（报销用）, `ofd`（官方格式）, `xml`（机器可读）— 通常只需 PDF

---

## 51发票 (51fapiao)

**发件人:** `dzfp@51fapiao.cloud`

**邮件特征:** 邮件直接携带 PDF 和/或 ZIP 附件。

**浏览器下载流程:**
1. 打开邮件
2. 找到附件区域的下载按钮
3. 点击下载 PDF（或 ZIP 后本地解压取 PDF）

---

## fapiao.com

**发件人:** `service@fapiao.com.cn`

**邮件特征:** 正文包含直接下载链接:
```
https://www.fapiao.com/dzfp-web/pdf/download?request={TOKEN}
https://www.fapiao.com/DownLoad/ofd/download?request={TOKEN}
```

**⚠️ 注意:** 链接约 30 天后过期。过期后检查邮件中的 QR 码图片。

**浏览器下载流程:**
1. 提取邮件正文中的下载链接
2. 在新标签页打开链接 → 直接触发下载
3. 如果链接过期（404），查找邮件中的 QR 码:
   - 提取 `data:image/png;base64,...` 格式的图片
   - 解码 QR 码获取备用 URL

---

## 滴滴出行 (Didi)

**发件人:** `didifapiao@mailgate.xiaojukeji.com`

**邮件特征:** 直接携带 PDF 附件（发票 + 行程单）。

**浏览器下载流程:**
1. 打开邮件
2. 找到 PDF 附件的下载按钮
3. 点击下载

**去重:** 同一天可能收到多张发票，用邮件时间戳区分文件名。

**分类:** → transport/didi/

---

## 中国移动 (China Mobile)

**发件人:** `10086@139.com`

**邮件特征:** ZIP 附件，内含 PDF + OFD + XML 三种格式。

**浏览器下载流程:**
1. 打开邮件，下载 ZIP 附件
2. 本地解压 ZIP
3. 只保留 PDF 文件

**分类:** → telecom/

---

## Tim Hortons China

**发件人:** `Invoice@store.timschina.com`

**邮件特征:** 正文包含 xforceplus 短链接:
```
https://s.xforceplus.com/XXXXX
```

**浏览器下载流程:**
1. 提取链接
2. 在新标签页打开 → 直接下载 PDF

**分类:** → dining/

---

## Marriott Hotels / 万豪酒店

**发件人:** `mhrs.*.gsm@marriott.com`

**邮件特征:** E-Folio（水单）作为 PDF 附件。

**浏览器下载流程:**
1. 打开邮件，下载 PDF 附件

**酒店发票:** 通常由酒店财务部门另外发送，可能来自:
- 个人邮箱（`@163.com`, `@qq.com`）
- 百望云平台
- 需要通过酒店名称 + 日期匹配水单和发票

**分类:** → accommodation/

---

## 通用规则

### 链接提取的黄金法则

```python
# ❌ 错误 — 只取 href，拿到的是追踪链接（会过期）
hrefs = re.findall(r'href="([^"]+)"', html)

# ✅ 正确 — 同时取 display text 中的真实 URL
for match in re.finditer(r'<a[^>]+href="[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL):
    link_text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
    if re.match(r'https?://', link_text):
        real_urls.append(link_text)
```

### QR 码是备用方案

当链接过期时，邮件中嵌入的 QR 码图片通常仍然有效。查找 `data:image/png;base64,...` 格式的图片，解码 QR 码获取下载 URL。

### 中国电子发票三件套

中国电子发票通常以 ZIP 包形式发送，内含:
- **PDF** — 人类可读，报销用 ✅
- **OFD** — 官方格式（Open Fixed-layout Document）
- **XML** — 机器可读

报销通常只需要 PDF。

### 发票平台识别优先级

```
1. 发件人精确匹配（最可靠）
2. 邮件正文中的平台域名（baiwang.com, fapiao.com, xforceplus.com）
3. 附件文件名模式（"电子发票", "行程单"）
4. Agent 语义判断（兜底）
```
