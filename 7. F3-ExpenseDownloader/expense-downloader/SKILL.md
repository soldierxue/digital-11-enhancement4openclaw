---
name: expense-downloader
description: >
  通过浏览器自动化（Chrome DevTools Protocol）从用户已登录的邮箱页面中识别、下载并分类
  Expense 报销材料（发票、水单、收据等）。支持 Gmail 和 163 邮箱。
  处理 PDF 附件、ZIP 包、链接下载、中国发票平台（百望云、滴滴、fapiao.com 等）。
  不需要 OAuth API 认证，依赖 DCV 远程桌面 + Chrome CDP 操作用户已登录的浏览器。
  Activate when: 用户要求下载发票, 下载水单, 整理报销材料, expense, invoice,
  发票下载, 水单下载, 报销, reimbursement, download invoices, 收据,
  receipt, folio, 账单, 行程单, 报销单。
---

# Expense Downloader — 邮箱发票/水单自动下载与分类

通过 CDP 操作用户已登录的邮箱浏览器页面，自动识别近 3 个月内的 Expense 相关邮件，
下载发票/水单/收据等附件，并按费用类型分类归档。

## Prerequisites

- DCV 远程桌面环境已配置（参考 `1. DCV_on_Ubuntu`）
- Chrome + CDP 已配置（参考 `2. Chrome_DevTool`）
  - `browser.enabled = true`
  - user profile CDP 端口可用（9222 或 18800）
- 用户已在 Chrome 中打开并登录邮箱页面（Gmail 或 163 邮箱）
- Python 3.8+，`websocket-client` 已安装

## Configuration

默认输出目录: `~/Expenses/`

```bash
# 可通过环境变量覆盖
export EXPENSE_OUTPUT_DIR=~/Expenses
export EXPENSE_CDP_URL=http://127.0.0.1:9222
export EXPENSE_MONTHS=3          # 扫描最近几个月，默认 3
```

## Workflow

### Phase 0: 环境检查

1. 检查 CDP 端口是否可用:
   ```bash
   curl -s http://127.0.0.1:9222/json/list
   ```
2. 列出当前标签页，识别邮箱页面:
   - 匹配域名: `mail.google.com`, `mail.163.com`, `mail.126.com`
3. 如果没有邮箱标签页 → 提示用户先打开并登录邮箱
4. 识别邮箱类型 → 选择对应的 DOM 适配器

### Phase 1: 扫描邮件列表

```bash
python3 SKILL_DIR/scripts/scan_inbox.py \
  --cdp-url http://127.0.0.1:9222 \
  --months 3 \
  --output /tmp/expense-scan-result.json
```

流程:
1. 连接到邮箱标签页
2. 利用邮箱搜索功能输入关键词预筛选:
   - Gmail: `newer_than:90d (发票 OR invoice OR 水单 OR folio OR 收据 OR receipt OR 账单 OR bill OR 行程单 OR 报销单)`
   - 163邮箱: `发票 OR invoice OR 水单 OR folio OR 收据 OR receipt OR 账单 OR bill OR 行程单 OR 报销单`
3. 等待搜索结果加载
4. 提取邮件列表中每封邮件的摘要信息（subject, sender, date, hasAttachment, snippet）
5. 输出结构化 JSON

**邮箱适配器:** 脚本内置 Gmail / 163邮箱 的 DOM 选择器。
选择器失效时，Agent 可通过 `take_snapshot` 获取当前 DOM，动态调整。

### Phase 2: AI 识别 Expense 邮件

此步骤由 Agent（而非脚本）完成:
1. 读取 Phase 1 输出的 JSON
2. 对每封邮件，综合 subject + sender + snippet 判断是否为 Expense 材料
3. 判断依据:
   - **正面关键词**: 发票, invoice, 水单, folio, 收据, receipt, 账单, bill, 行程单, 报销单
   - **负面关键词**: 退票, 还款提醒, 预订确认, 对账单, 周报, unsubscribe, 广告, 促销
   - **高置信发件人**: `*@baiwang.com`, `dzfp@51fapiao.cloud`, `didifapiao@*`,
     `*@fapiao.com.cn`, `10086@139.com`, `Invoice@*`, `mhrs.*.gsm@marriott.com`
   - **语义理解**: Agent 综合判断
4. 输出: 标记为 Expense 的邮件索引列表 + 预判费用类型

### Phase 3: 下载 Expense 材料

```bash
python3 SKILL_DIR/scripts/download_expense.py \
  --cdp-url http://127.0.0.1:9222 \
  --email-indices "0,2,5,8" \
  --output-dir ~/Expenses \
  --scan-result /tmp/expense-scan-result.json
```

对每封标记的邮件:
1. 点击打开邮件
2. 执行决策树:
   ```
   有 PDF 附件 → 点击下载
   有 ZIP 附件 → 点击下载（后续本地解压取 PDF）
   无附件 → 提取正文链接
     ├── 提取 <a> 标签 display text（非 href！关键经验）
     ├── 识别发票平台链接 → 新标签页打开 → 找下载按钮 → 点击
     ├── 直接 PDF 链接 → 导航下载
     └── QR 码图片 → 解码 URL → 尝试下载
   ```
3. 通过 CDP `Browser.setDownloadBehavior` 指定下载目录
4. 监控下载完成
5. 返回邮件列表，处理下一封

**RAW 文件夹命名:** 下载完成后，根据邮件中发票的最早和最晚日期，
自动将临时下载目录重命名为:
```
~/Expenses/[provider]_[earliest_date]_to_[latest_date]/
```
示例:
```
~/Expenses/[163]_[2026.02.01]_to_[2026.03.31]/
~/Expenses/[gmail]_[2026.01.15]_to_[2026.03.10]/
```

**中国发票平台处理:** 参考 `references/platforms.md`

### Phase 4: 分类归档

```bash
python3 SKILL_DIR/scripts/classify_expense.py \
  --input-dir "~/Expenses/[163]_[2026.02.01]_to_[2026.03.31]" \
  --output-dir ~/Expenses \
  --scan-result /tmp/expense-scan-result.json
```

按费用类型分类:
- 🚗 交通 (transport/) — 滴滴、航空、火车
- 🏨 住宿 (accommodation/) — 酒店水单/发票
- 🍽️ 餐饮 (dining/) — 餐厅发票
- 📱 通讯 (telecom/) — 移动/联通/电信
- 💻 办公 (office/) — 办公用品
- 📋 其他 (other/) — 未分类

**发票文件智能重命名:**

每个发票文件根据其内容信息重命名，格式:
```
YYYYMMDD_类型_金额_地点_供应商.pdf
```

示例:
- `20260115_发票_58.50元_北京_滴滴出行.pdf`
- `20260118_水单_1280.00元_上海_Marriott.pdf`
- `20260201_发票_89.00元_广州_中国移动.pdf`
- `20260210_行程单_1560.00元_北京-上海_东方航空.pdf`

信息提取优先级:
1. **Kiro CLI 发票识别（OCR/AI）** — 对 PDF/图片文件调用 Kiro CLI 提取日期、金额、供应商、地点等
2. **邮件元数据** — 从发件人、主题、日期等字段提取
3. **文件名模式** — 从原始文件名中提取
4. **兜底** — 使用下载日期 + 默认类型

> 可通过 `--no-ocr` 参数禁用 Kiro CLI 识别（仅依赖邮件元数据）

输出目录结构:
```
~/Expenses/
├── [163]_[2026.02.01]_to_[2026.03.31]/   ← RAW 原始下载
│   ├── 原始文件1.pdf
│   ├── 原始文件2.pdf
│   └── download-result.json
├── YYYY-MM/                                ← 分类归档
│   ├── transport/didi/
│   ├── transport/flight/
│   ├── accommodation/
│   ├── dining/
│   ├── telecom/
│   └── other/
├── summary.json
└── summary.md
```

### Phase 5: 生成汇总报告

自动生成 `summary.md`:
- 扫描/识别/下载统计
- 按类别的文件明细
- 需要人工处理的项目（链接过期、格式不支持等）

向用户汇报结果。

## Script Options

### scan_inbox.py

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--cdp-url` | `http://127.0.0.1:9222` | CDP 地址 |
| `--tab-url` | (自动检测) | 匹配邮箱标签页的关键词 |
| `--months` | `3` | 扫描最近几个月 |
| `--output` | `/tmp/expense-scan-result.json` | 输出 JSON 路径 |
| `--provider` | (自动检测) | 强制指定邮箱类型: gmail, 163 |

### download_expense.py

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--cdp-url` | `http://127.0.0.1:9222` | CDP 地址 |
| `--email-indices` | (必填) | 要下载的邮件索引，逗号分隔 |
| `--output-dir` | `~/Expenses` | 下载根目录（RAW 子目录自动创建） |
| `--scan-result` | (必填) | Phase 1 输出的 JSON |
| `--timeout` | `30` | 单个下载超时秒数 |

### classify_expense.py

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input-dir` | (自动检测) | RAW 文件夹路径（如 `~/Expenses/[163]_[...]`） |
| `--output-dir` | `~/Expenses` | 归档根目录 |
| `--scan-result` | (可选) | 邮件元数据，辅助分类 |
| `--download-result` | (可选) | download_expense.py 输出的 JSON |
| `--no-ocr` | `false` | 禁用 Kiro CLI 发票内容识别 |

## State

文件: `state.json`

```json
{
  "lastScanTime": 0,
  "lastScanProvider": "",
  "processedEmailIds": [],
  "totalScanned": 0,
  "totalDownloaded": 0
}
```

| 字段 | 说明 |
|------|------|
| `lastScanTime` | 上次扫描 Unix 时间戳 |
| `lastScanProvider` | 上次扫描的邮箱类型 |
| `processedEmailIds` | 已处理邮件 ID（增量去重） |
| `totalScanned` | 累计扫描邮件数 |
| `totalDownloaded` | 累计下载文件数 |

## References

| 文件 | 内容 |
|------|------|
| `references/platforms.md` | 中国发票平台下载模式（百望云、滴滴、fapiao.com 等） |
| `references/email-providers.md` | Gmail 和 163 邮箱 Web 端 DOM 选择器参考 |
| `references/expense-categories.md` | 费用分类规则定义 |

## Troubleshooting

| 问题 | 处理 |
|------|------|
| CDP 端口无响应 | 检查 Chrome Remote Debugging 是否启用；参考 `2. Chrome_DevTool` |
| 未找到邮箱标签页 | 在 Chrome 中打开并登录邮箱（Gmail 或 163），确保页面完全加载 |
| 邮箱搜索无结果 | 检查搜索关键词是否正确；手动在邮箱中测试同样的搜索 |
| 附件下载超时 | 增大 `--timeout`；检查网络连接 |
| 发票平台链接过期 | 标记为失败，尝试 QR 码路径；参考 `references/platforms.md` |
| 163邮箱 iframe 问题 | 163邮箱使用 iframe 嵌套，脚本已内置多层 iframe 处理逻辑 |
| ZIP 解压失败 | 文件可能损坏，标记为需人工处理 |
| 分类错误 | 调整 `references/expense-categories.md` 中的规则 |
| websocket-client 未安装 | `pip3 install --break-system-packages websocket-client` |
| Kiro CLI 识别失败 | 检查 `kiro-cli` 是否已安装并可用；可用 `--no-ocr` 跳过识别 |
| RAW 文件夹名称异常 | 邮件日期解析失败时使用当前日期；检查邮件日期格式 |
