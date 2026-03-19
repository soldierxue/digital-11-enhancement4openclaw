# F3-InvoiceDownloader — 基于浏览器自动化的邮箱发票/水单下载与分类

> 通过 DCV 远程桌面 + Chrome DevTools Protocol，在用户已登录的邮箱页面中自动识别、下载并分类 Expense 报销材料（发票、水单、收据等）。

---

## 一、Gmail Invoice Downloader 参考分析

### 1.1 原方案架构

原 `gmail-invoice-downloader` 采用 **Gmail API + OAuth2** 方案：

```
用户 → Google Cloud Console 创建 OAuth 凭证
    → gmail-auth.py 授权获取 token.json
    → gmail-helper.py / download-invoices.py 通过 REST API 操作邮箱
```

**核心能力：**
- Gmail API 搜索（`gmail.readonly` 权限）
- 附件直接下载（PDF/ZIP via API）
- 邮件正文链接提取与下载
- QR 码解码获取下载链接

### 1.2 可复用的经验（✅ 直接采纳）

| 经验 | 说明 | 复用方式 |
|------|------|----------|
| **搜索关键词体系** | `发票 OR invoice OR 水单 OR folio OR 收据 OR receipt OR 账单 OR bill OR 行程单 OR 报销单` | 作为邮件列表筛选的语义匹配关键词 |
| **邮件处理决策树** | 有 PDF 附件 → 有 ZIP 附件 → 无附件提取链接 → QR 码 | 完整复用，改为浏览器操作实现 |
| **链接提取：取 display text 而非 href** | 营销邮件的 `<a>` 标签 href 是追踪链接（会过期），display text 才是真实 URL | 在浏览器 JS 中实现同样逻辑 |
| **中国发票平台模式** | 百望云 URL 模式、滴滴直接附件、fapiao.com 链接、中国移动 ZIP 等 | 作为平台识别规则库 |
| **文件去重命名** | `filename (N).pdf` 后缀递增 | 直接复用 |
| **跳过非发票邮件** | 排除关键词：退票、还款提醒、预订确认、对账单、周报 | 作为负面过滤规则 |
| **ZIP 处理** | 中国电子发票常为 ZIP（含 PDF + OFD + XML），只保留 PDF | 下载后本地处理 |

### 1.3 不适用的部分（❌ 需替换）

| 原方案 | 问题 | 我们的替代方案 |
|--------|------|---------------|
| Gmail API OAuth2 认证 | 需要 Google Cloud Console 配置，流程复杂 | 用户在 DCV 桌面手动登录邮箱，Agent 通过 CDP 操作已登录页面 |
| REST API 读取邮件 | 依赖 token.json，有过期和刷新问题 | 浏览器已登录，直接操作 DOM |
| API 下载附件 | 需要 attachmentId + API 调用 | 浏览器内点击下载按钮/链接 |
| 仅支持 Gmail | API 绑定 Gmail | 浏览器方案支持多种 Web 邮箱（Gmail、163 邮箱） |

### 1.4 新增能力（🆕 原方案没有）

| 能力 | 说明 |
|------|------|
| **多邮箱支持** | 支持 Gmail 和 163 邮箱，用户打开哪个邮箱就操作哪个 |
| **AI 语义识别** | 不仅靠关键词，还通过 Agent 理解邮件上下文判断是否为 Expense 相关 |
| **自动分类归档** | 按费用类型（交通、住宿、餐饮、通讯等）自动分类存放 |
| **元数据提取** | 从发票内容提取金额、日期、供应商等结构化信息 |
| **浏览器内下载** | 利用浏览器已有的登录态，无需额外认证 |

---

## 二、Skill 设计方案

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户 DCV 远程桌面                       │
│                                                         │
│  ┌──────────────┐    ┌──────────────────────────────┐   │
│  │ Chrome 浏览器 │    │ OpenClaw / Kiro Agent        │   │
│  │ (用户已登录   │◄──►│                              │   │
│  │  邮箱页面)    │CDP │  ┌────────────────────────┐  │   │
│  └──────────────┘    │  │ expense-downloader     │  │   │
│                      │  │ Skill                  │  │   │
│                      │  │                        │  │   │
│                      │  │ Phase 1: 扫描邮件列表  │  │   │
│                      │  │ Phase 2: 识别 Expense  │  │   │
│                      │  │ Phase 3: 下载附件/链接  │  │   │
│                      │  │ Phase 4: 分类归档       │  │   │
│                      │  └────────────────────────┘  │   │
│                      └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 依赖关系

```
前置依赖:
  1. DCV_on_Ubuntu (1. DCV_on_Ubuntu)     — 提供图形桌面环境
  2. Chrome_DevTool (2. Chrome_DevTool)   — 提供 Chrome + CDP 能力
     └── browser.enabled = true
     └── user profile (CDP 9222) 或 attachOnly 模式

运行时依赖:
  - 用户已在 Chrome 中打开并登录邮箱页面（Gmail / 163邮箱）
  - CDP 端口可用（9222 或 18800）
  - Python 3.8+ (websocket-client)
```

### 2.3 目录结构

```
7. F3-ExpenseDownloader/
├── README.md                              # 本文件
└── expense-downloader/                    # Skill 目录
    ├── SKILL.md                           # Skill 定义（Agent 读取）
    ├── state.json                         # 运行状态
    ├── references/
    │   ├── platforms.md                   # 中国发票平台下载模式（复用 gmail 版）
    │   ├── email-providers.md             # 各邮箱 Web 端 DOM 结构参考
    │   └── expense-categories.md          # 费用分类规则定义
    └── scripts/
        ├── scan_inbox.py                  # Phase 1: 扫描邮件列表
        ├── download_expense.py            # Phase 2+3: 识别并下载 Expense 材料
        └── classify_expense.py            # Phase 4: 分类归档
```

### 2.4 Workflow 设计

#### Phase 0: 环境检查（前置）

```
1. 检查 CDP 端口是否可用
   curl -s http://127.0.0.1:9222/json/list (或 18800)

2. 列出当前打开的标签页，识别邮箱页面
   - 匹配: mail.google.com, mail.163.com, mail.126.com

3. 如果没有找到邮箱标签页 → 提示用户先打开并登录邮箱

4. 识别邮箱类型 → 选择对应的 DOM 适配器
```

#### Phase 1: 扫描邮件列表（scan_inbox.py）

核心思路：在用户已登录的邮箱页面中，通过 CDP 执行 JS 读取邮件列表 DOM。

```
输入: CDP 连接 + 邮箱标签页
输出: 邮件摘要列表 JSON（subject, sender, date, hasAttachment, snippet）

流程:
1. 连接到邮箱标签页的 WebSocket
2. 根据邮箱类型，使用对应的 DOM 选择器提取邮件列表
3. 默认扫描范围：最近 3 个月的邮件
   - Gmail: 使用搜索框输入 "newer_than:90d (发票 OR invoice OR 水单 ...)"
   - 163邮箱: 使用搜索框输入关键词（不支持日期运算符，需后续按日期过滤）
   - 通用: 滚动加载 + 逐条读取
4. 提取每封邮件的:
   - 主题 (subject)
   - 发件人 (sender)
   - 日期 (date)
   - 是否有附件标记 (hasAttachment)
   - 摘要片段 (snippet)
5. 输出结构化 JSON 供 Agent 分析
```

**邮箱适配器设计（类似 web-article-saver 的 SITE_ADAPTERS）：**

```python
EMAIL_ADAPTERS = {
    "mail.google.com": {
        "name": "Gmail",
        "search_box": "input[aria-label='Search mail']",
        "email_row": "tr.zA",
        "subject_selector": ".bog span",
        "sender_selector": ".yW span[email]",
        "date_selector": ".xW span",
        "attachment_indicator": ".yf img, .brd",
        "snippet_selector": ".y2",
        "search_query_template": "newer_than:90d ({keywords})",
    },
    "mail.163.com": {
        "name": "163邮箱",
        "search_box": "#search-key, input.nui-ipt-input",
        "email_row": ".nM0 .nM1, div[data-mrid], tr[oid]",
        "subject_selector": ".nM3, .subjectText",
        "sender_selector": ".nM2, .sender",
        "date_selector": ".nM5, .time",
        "attachment_indicator": ".nM4 img, .icon-attachment",
        "snippet_selector": "",
        "search_query_template": "{keywords}",
        # 注意: 163 邮箱使用 iframe 结构，需在 mainFrame 中操作
    },
}
```

#### Phase 2: AI 识别 Expense 邮件

这一步由 Agent（而非脚本）完成，利用 LLM 的语义理解能力：

```
输入: Phase 1 输出的邮件摘要列表 JSON
处理: Agent 分析每封邮件，判断是否为 Expense 相关

判断依据（优先级从高到低）:
1. 关键词精确匹配:
   正面: 发票, invoice, 水单, folio, 收据, receipt, 账单, bill, 行程单, 报销单
   负面: 退票, 还款提醒, 预订确认, 对账单, 周报, unsubscribe, 广告

2. 发件人模式匹配:
   高置信: *@baiwang.com, dzfp@51fapiao.cloud, didifapiao@*,
           *@fapiao.com.cn, 10086@139.com, Invoice@*
   中置信: *@marriott.com, *@hilton.com, *@hotel*, noreply@*

3. 语义理解:
   Agent 综合主题+发件人+摘要，判断是否为报销材料

输出: 标记为 Expense 的邮件 ID 列表 + 置信度 + 预判类型
```

#### Phase 3: 下载 Expense 材料（download_expense.py）

对每封被标记的邮件，通过浏览器操作下载：

```
输入: 邮件 ID 列表 + CDP 连接
输出: 下载的文件列表

流程（对每封邮件）:
1. 在邮箱页面中点击打开该邮件
2. 等待邮件内容加载完成
3. 执行决策树:
   ├── 检测到附件区域
   │   ├── PDF 附件 → 点击下载按钮
   │   ├── ZIP 附件 → 点击下载，后续本地解压取 PDF
   │   └── 其他格式 → 记录跳过
   │
   └── 无附件 → 提取邮件正文中的链接
       ├── 提取 <a> 标签的 display text（非 href！）
       ├── 识别发票平台链接（百望云、fapiao.com 等）
       │   └── 在新标签页打开链接 → 找到下载按钮 → 点击下载
       ├── 识别直接 PDF 链接 → 导航下载
       └── 检查 QR 码图片 → 解码获取 URL → 尝试下载

4. 监控 Chrome 下载目录，确认文件下载完成
5. 将文件移动到统一的 output 目录
6. 返回邮件列表页，处理下一封
```

**关键技术点：**

```python
# 通过 CDP 监控下载事件
cdp.send("Browser.setDownloadBehavior", {
    "behavior": "allowAndName",
    "downloadPath": "/tmp/expense-downloads",
    "eventsEnabled": True
})

# 通过 CDP 点击下载按钮（示例：Gmail 附件下载）
cdp.evaluate("""
    // Gmail 附件下载按钮
    const downloadBtn = document.querySelector('[data-tooltip="Download"]');
    if (downloadBtn) downloadBtn.click();
""")

# 等待下载完成
# 监听 Browser.downloadProgress 事件，state == "completed"
```

#### Phase 4: 分类归档（classify_expense.py）

```
输入: 下载的文件列表 + 邮件元数据
输出: 按类别归档的文件 + 汇总报告

分类规则:
├── 🚗 交通 (Transportation)
│   ├── 滴滴出行发票 → transport/didi/
│   ├── 航空行程单 → transport/flight/
│   ├── 火车票 → transport/train/
│   └── 其他交通 → transport/other/
│
├── 🏨 住宿 (Accommodation)
│   ├── 酒店水单/发票 → accommodation/
│   └── Airbnb 收据 → accommodation/
│
├── 🍽️ 餐饮 (Dining)
│   └── 餐厅发票 → dining/
│
├── 📱 通讯 (Telecom)
│   ├── 中国移动 → telecom/
│   ├── 中国联通 → telecom/
│   └── 中国电信 → telecom/
│
├── 💻 办公 (Office)
│   └── 办公用品发票 → office/
│
└── 📋 其他 (Other)
    └── 未分类 → other/

分类依据:
1. 发件人邮箱域名匹配（如 didifapiao@* → 交通/滴滴）
2. 邮件主题关键词
3. PDF 文件名模式
4. Agent 语义判断（兜底）

输出目录结构:
output/
├── YYYY-MM/                          # 按月份组织
│   ├── transport/
│   │   ├── didi/
│   │   │   ├── 20260115_滴滴电子发票.pdf
│   │   │   └── 20260120_滴滴电子发票.pdf
│   │   └── flight/
│   │       └── 20260210_航空行程单.pdf
│   ├── accommodation/
│   │   └── 20260118_Marriott_水单.pdf
│   ├── telecom/
│   │   └── 20260201_中国移动发票.pdf
│   └── other/
│       └── 20260205_unknown_invoice.pdf
├── summary.json                      # 结构化汇总
└── summary.md                        # 人类可读汇总报告
```

**汇总报告 (summary.md) 格式：**

```markdown
# Expense 下载汇总 — YYYY-MM-DD

## 📊 统计
- 扫描邮件: N 封
- 识别 Expense: M 封
- 成功下载: X 个文件
- 下载失败: Y 个

## 📁 分类明细
| 类别 | 数量 | 金额(如可提取) | 文件 |
|------|------|----------------|------|
| 交通 | 5 | ¥1,234.56 | didi×3, flight×2 |
| 住宿 | 2 | ¥2,800.00 | marriott×2 |
| ... | | | |

## ⚠️ 需要人工处理
- [邮件主题] — 链接已过期，需手动下载
- [邮件主题] — 无法识别附件格式
```

### 2.5 SKILL.md 核心定义（草案）

```yaml
---
name: expense-downloader
description: >
  通过浏览器自动化（CDP）从用户已登录的邮箱页面中识别、下载并分类 Expense 报销材料。
  支持 Gmail 和 163 邮箱。
  处理 PDF 附件、ZIP 包、链接下载、中国发票平台（百望云、滴滴、fapiao.com 等）。
  Activate when: 用户要求下载发票, 下载水单, 整理报销材料, expense, invoice, 
  发票下载, 水单下载, 报销, reimbursement, download invoices。
---
```

### 2.6 状态管理

```json
// state.json
{
  "lastScanTime": 0,
  "lastScanEmailProvider": "",
  "processedEmailIds": [],
  "downloadedFiles": [],
  "totalScanned": 0,
  "totalDownloaded": 0
}
```

| 字段 | 说明 |
|------|------|
| `lastScanTime` | 上次扫描的 Unix 时间戳 |
| `lastScanEmailProvider` | 上次扫描的邮箱类型 |
| `processedEmailIds` | 已处理的邮件 ID（避免重复下载） |
| `downloadedFiles` | 已下载文件的路径列表 |

### 2.7 与现有 Skill 的关系

```
1. DCV_on_Ubuntu        ← 提供图形桌面（必须）
2. Chrome_DevTool       ← 提供 Chrome + CDP（必须）
   └── web-article-saver  ← 复用 CDPClient 类和 find_tab 模式
5. F1-TechUpdate        ← 无直接关系
6. F2-TechWriter        ← 无直接关系
7. F3-ExpenseDownloader ← 本 Skill（新增）
```

---

## 三、关键技术挑战与应对

### 3.1 邮箱 DOM 结构差异大

**挑战：** Gmail 和 163 邮箱的 DOM 结构完全不同，且经常变化。163 邮箱还使用多层 iframe 嵌套。

**应对：**
- 采用适配器模式（`EMAIL_ADAPTERS`），每个邮箱一套选择器
- 优先使用邮箱自带的搜索功能缩小范围（输入关键词搜索），而非遍历全部邮件
- 选择器失效时，Agent 可通过 `take_snapshot` 获取当前 DOM 结构，动态调整

### 3.2 附件下载的浏览器行为

**挑战：** 浏览器下载文件是异步的，且下载路径不确定。

**应对：**
- 通过 CDP `Browser.setDownloadBehavior` 指定下载目录
- 监听 `Browser.downloadProgress` 事件等待完成
- 设置超时机制（30s），超时标记为失败

### 3.3 发票平台链接需要在新标签页操作

**挑战：** 百望云等平台链接打开后是 SPA 页面，需要找到下载按钮。

**应对：**
- 在新标签页打开链接（`cdp.send("Target.createTarget", {"url": ...})`）
- 等待页面加载完成
- 根据 `references/platforms.md` 中的平台模式，定位下载按钮
- 下载完成后关闭标签页

### 3.4 三个月邮件量可能很大

**挑战：** 3 个月的邮件可能有数百封，全部扫描耗时长。

**应对：**
- 利用邮箱搜索功能预筛选（关键词搜索），大幅减少候选邮件数
- Agent 对搜索结果做快速语义过滤，只对高置信邮件执行下载
- 支持增量模式：`state.json` 记录已处理邮件，避免重复

---

## 四、执行计划

### 阶段 1：基础框架
- [ ] 创建 `expense-downloader/` 目录结构
- [ ] 编写 SKILL.md
- [ ] 实现 `scan_inbox.py`（Gmail 适配器优先）
- [ ] 实现基础 `download_expense.py`（PDF 附件下载）

### 阶段 2：完善下载能力
- [ ] 添加 ZIP 处理
- [ ] 添加链接提取与下载（含 display text 提取）
- [ ] 添加中国发票平台支持（百望云、fapiao.com）
- [ ] 编写 `references/platforms.md`

### 阶段 3：分类与归档
- [ ] 实现 `classify_expense.py`
- [ ] 编写 `references/expense-categories.md`
- [ ] 生成汇总报告

### 阶段 4：163 邮箱支持
- [ ] 添加 163 邮箱适配器（含 iframe 处理）
- [ ] 编写 `references/email-providers.md`
