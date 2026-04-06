---
name: tech-updates-collector
description: >
  按六大主题从 Twitter/X、博客、论文等来源采集 AI 资讯，生成结构化日报。
  通过 kiro-cli 调用 Exa MCP 工具执行搜索。
  支持增量模式：每次只搜索上次检查之后的新内容，追加到当天日报。
  Activate when: heartbeat 定时触发, 或用户要求执行 AI 日报采集,
  tech updates, 日报, 采集, AI资讯, 技术更新, 每日更新。
---

# Tech Updates Collector

按六大主题从 Twitter/X、博客、论文等来源采集 AI 资讯，生成结构化日报 `output/YYYY-MM-DD.md`。

**核心机制：增量采集 + 追加输出**

> ⚠️ **注意事项**
>
> **采集域名黑名单**（已被白名单机制取代，保留为历史记录）：
> ~~以下网站为投资分析类二手信息源，已从搜索中排除~~
> - ~~fool.com / motleyfool.com~~
> - ~~seekingalpha.com~~
> - ~~investorplace.com~~
> - ~~zacks.com~~
>
> ~~如需扩展黑名单，在各 search query 中追加 `-site:domain.com`~~
>
> ---
>
> **⚠️ 采集域名白名单（强制）**：所有 Exa 搜索必须通过 `includeDomains` 参数限制在以下白名单域名内。
> 白名单外的域名结果**一律不采纳**，不进入日报。
>
> **设计原则**：
> - Tier 1（顶级媒体）：TechCrunch / Reuters / Bloomberg / 36kr 等
> - Tier 2（官方渠道）：各大公司主站（anthropic.com / openai.com / nvidia.com 等）— 发布即事实，无需核实
> - Tier 3（专业博客）：SemiAnalysis / HackerNews / arXiv 等
> - Tier 4（补充来源）：BleepingComputer / CNBC 等
>
> **白名单文件**：`~/.openclaw/workspace/output/source-whitelist.md`
>
> **完整白名单域名列表**：
> ```
> Tier 1 — 顶级科技媒体:
>   techcrunch.com, theverge.com, wired.com, arstechnica.com,
>   venturebeat.com, technologyreview.com, spectrum.ieee.org,
>   reuters.com, bloomberg.com, ft.com, wsj.com, nytimes.com,
>   fortune.com, foreignpolicy.com
> 中文科技媒体:
>   36kr.com, jiqizhixin.com, leiphone.com, infoq.com, caixin.com, huxiu.com
> Tier 2 — 公司官方主站（发布即事实）:
>   anthropic.com, openai.com,
>   deepmind.google, deepmind.com, research.google, blog.google, cloud.google.com,
>   microsoft.com, azure.microsoft.com, techcommunity.microsoft.com,
>   meta.com, ai.meta.com, engineering.fb.com,
>   nvidia.com, developer.nvidia.com,
>   aws.amazon.com, aboutamazon.com,
>   apple.com,
>   huggingface.co, mistral.ai, cohere.com, stability.ai,
>   deepseek.com, xai.com,
>   zhipuai.cn, moonshot.cn, minimax.io,
>   salesforce.com, servicenow.com, palantir.com,
>   databricks.com, snowflake.com,
>   cerebras.net, groq.com, together.ai,
>   pytorch.org, tensorflow.org
> Tier 2 — 学术/研究机构:
>   arxiv.org, openreview.net, acm.org, semanticscholar.org,
>   kpmg.com, mckinsey.com, gartner.com, idc.com, forrester.com, shrm.org
> Tier 3 — 高质量专业博客/社区:
>   semianalysis.com, stratechery.com, interconnects.ai,
>   simonwillison.net, news.ycombinator.com, github.com,
>   a16z.com, sequoiacap.com, ycombinator.com, crunchbase.com,
>   substack.com
> Tier 4 — 可接受补充来源:
>   bleepingcomputer.com, theregister.com, cnbc.com,
>   businessinsider.com, finance.yahoo.com,
>   economictimes.indiatimes.com, globeandmail.com, moneycontrol.com
> ```
- 每次运行只搜索 `lastCollectorCheck → now` 时间窗口的新内容
- 新结果追加到当天日报文件末尾
- 一天一个文件，多次运行共同积累

## Prerequisites

- Kiro CLI 已安装并登录（`kiro-cli auth status`）
- Exa MCP Server 已配置（`~/.kiro/settings/mcp.json` 中有 `exa` 条目）
- 验证: `kiro-cli chat --no-interactive --trust-all-tools "use Exa web_search_exa for: test query"`

## 主题分类与搜索策略

参考 `topics-definition.md`（Single Source of Truth），包含：

**六大主题**（输出分类维度）:
1. 🤖 **openclaw** — AI Agent 能力与平台
2. 🏢 **ai-org-structure** — AI 时代的组织变革
3. 💼 **agentic-cases** — AI Agent 实战案例
4. 🛒 **agentic-commerce** — AI 商业应用
5. 🏭 **enterprise-ai** — 企业 AI 应用
6. ⚙️ **ai-dlc** — AI 开发生命周期

**搜索策略维度** (Dimension A-G): 定义了 7 组搜索关键词和来源策略
**重点关注来源**: 行业领袖 Twitter 账号、特定博客（Gary Marcus 等）
**重点跟踪公司**: AI 基础模型公司、企业 AI 平台、云服务商、半导体等

> 搜索策略维度是采集阶段的组织方式，六大主题是输出阶段的分类方式。两者正交。

## Workflow

### Step 0: 计算搜索时间窗口

```python
import time, datetime

now = time.time()
lastCheck = state["lastCollectorCheck"]  # 从 state.json 读取

if lastCheck == 0 or (now - lastCheck) > 86400:
    # 首次运行 或 距上次超过 24h（服务器宕机恢复等）
    # 兜底：搜最近 24 小时
    startDate = now - 86400
else:
    # 增量模式：只搜上次检查之后的新内容
    startDate = lastCheck

endDate = now

# 格式化为 ISO 8601
startISO = datetime.datetime.utcfromtimestamp(startDate).strftime('%Y-%m-%dT%H:%M:%S.000Z')
endISO = datetime.datetime.utcfromtimestamp(endDate).strftime('%Y-%m-%dT%H:%M:%S.000Z')
```

**时间窗口示例**：
| 场景 | lastCheck | 搜索窗口 | 说明 |
|------|-----------|----------|------|
| 首次运行 | 0 | now-24h → now | 全量搜 24h |
| 常规增量（3h 间隔） | now-10800 | lastCheck → now | 仅搜 3h 新内容 |
| 宕机恢复（超过 24h） | now-172800 | now-24h → now | Cap 到 24h，避免窗口过大 |

### Step 1: 检查是否需要执行

```bash
# 读取 state.json 中的 lastCollectorCheck 时间戳
# 如果距上次执行不足 3 小时，跳过（避免过于频繁）
```

### Step 2: 执行搜索（通过 kiro-cli → Exa MCP）

按 `topics-definition.md` 中定义的 7 个搜索策略维度（Dimension A-G）执行。

**⚠️ 执行约束（防 OOM，c7g.large 仅 3.7GB RAM）**:
- **串行执行**：7 个维度必须逐个执行，等上一个完成后再启动下一个，**严禁并行**
- **单进程超时**：每个搜索命令加 `timeout 60` 前缀，超过 60 秒自动 kill
- **失败跳过**：某个维度搜索超时或失败，跳过继续下一个，不要重试

**⏰ 时间窗口（强制）**: 所有搜索使用 Step 0 计算的 `startISO` 和 `endISO`。
- 传参: `web_search_advanced_exa` 使用 `startPublishedDate` + `endPublishedDate`

**Search A — General AI/Tech News**:
```bash
timeout 60 kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search_advanced_exa: query='AI OR GenAI OR Anthropic OR Claude OR OpenAI OR DeepSeek OR semiconductors OR AI chips OR layoffs OR workforce', numResults=20, startPublishedDate='<startISO>', endPublishedDate='<endISO>', includeDomains=['techcrunch.com','theverge.com','wired.com','arstechnica.com','venturebeat.com','technologyreview.com','spectrum.ieee.org','reuters.com','bloomberg.com','ft.com','wsj.com','nytimes.com','fortune.com','foreignpolicy.com','36kr.com','jiqizhixin.com','leiphone.com','infoq.com','caixin.com','huxiu.com','anthropic.com','openai.com','deepmind.google','deepmind.com','research.google','blog.google','cloud.google.com','microsoft.com','azure.microsoft.com','techcommunity.microsoft.com','meta.com','ai.meta.com','engineering.fb.com','nvidia.com','developer.nvidia.com','aws.amazon.com','aboutamazon.com','apple.com','huggingface.co','mistral.ai','cohere.com','stability.ai','deepseek.com','xai.com','zhipuai.cn','moonshot.cn','minimax.io','salesforce.com','servicenow.com','palantir.com','databricks.com','snowflake.com','cerebras.net','groq.com','together.ai','pytorch.org','tensorflow.org','arxiv.org','openreview.net','acm.org','semanticscholar.org','kpmg.com','mckinsey.com','gartner.com','idc.com','forrester.com','shrm.org','semianalysis.com','stratechery.com','interconnects.ai','simonwillison.net','news.ycombinator.com','github.com','a16z.com','sequoiacap.com','ycombinator.com','crunchbase.com','substack.com','bleepingcomputer.com','theregister.com','cnbc.com','businessinsider.com','finance.yahoo.com','economictimes.indiatimes.com','globeandmail.com','moneycontrol.com']"
```

**Search B — Industry Leaders**:
```bash
timeout 60 kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search_advanced_exa: query='Sam Altman OR Elon Musk OR Satya Nadella OR Sundar Pichai OR Andrej Karpathy OR Yann LeCun AI announcement', numResults=15, startPublishedDate='<startISO>', endPublishedDate='<endISO>', includeDomains=['techcrunch.com','theverge.com','wired.com','arstechnica.com','venturebeat.com','technologyreview.com','spectrum.ieee.org','reuters.com','bloomberg.com','ft.com','wsj.com','nytimes.com','fortune.com','foreignpolicy.com','36kr.com','jiqizhixin.com','leiphone.com','infoq.com','caixin.com','huxiu.com','anthropic.com','openai.com','deepmind.google','deepmind.com','research.google','blog.google','cloud.google.com','microsoft.com','azure.microsoft.com','techcommunity.microsoft.com','meta.com','ai.meta.com','engineering.fb.com','nvidia.com','developer.nvidia.com','aws.amazon.com','aboutamazon.com','apple.com','huggingface.co','mistral.ai','cohere.com','stability.ai','deepseek.com','xai.com','zhipuai.cn','moonshot.cn','minimax.io','salesforce.com','servicenow.com','palantir.com','databricks.com','snowflake.com','cerebras.net','groq.com','together.ai','pytorch.org','tensorflow.org','arxiv.org','openreview.net','acm.org','semanticscholar.org','kpmg.com','mckinsey.com','gartner.com','idc.com','forrester.com','shrm.org','semianalysis.com','stratechery.com','interconnects.ai','simonwillison.net','news.ycombinator.com','github.com','a16z.com','sequoiacap.com','ycombinator.com','crunchbase.com','substack.com','bleepingcomputer.com','theregister.com','cnbc.com','businessinsider.com','finance.yahoo.com','economictimes.indiatimes.com','globeandmail.com','moneycontrol.com']"
```

**Search C — Enterprise AI**:
```bash
timeout 60 kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search_advanced_exa: query='Palantir OR Salesforce OR ServiceNow OR Workday OR Agentforce enterprise AI', numResults=15, startPublishedDate='<startISO>', endPublishedDate='<endISO>', includeDomains=['techcrunch.com','theverge.com','wired.com','arstechnica.com','venturebeat.com','technologyreview.com','spectrum.ieee.org','reuters.com','bloomberg.com','ft.com','wsj.com','nytimes.com','fortune.com','foreignpolicy.com','36kr.com','jiqizhixin.com','leiphone.com','infoq.com','caixin.com','huxiu.com','anthropic.com','openai.com','deepmind.google','deepmind.com','research.google','blog.google','cloud.google.com','microsoft.com','azure.microsoft.com','techcommunity.microsoft.com','meta.com','ai.meta.com','engineering.fb.com','nvidia.com','developer.nvidia.com','aws.amazon.com','aboutamazon.com','apple.com','huggingface.co','mistral.ai','cohere.com','stability.ai','deepseek.com','xai.com','zhipuai.cn','moonshot.cn','minimax.io','salesforce.com','servicenow.com','palantir.com','databricks.com','snowflake.com','cerebras.net','groq.com','together.ai','pytorch.org','tensorflow.org','arxiv.org','openreview.net','acm.org','semanticscholar.org','kpmg.com','mckinsey.com','gartner.com','idc.com','forrester.com','shrm.org','semianalysis.com','stratechery.com','interconnects.ai','simonwillison.net','news.ycombinator.com','github.com','a16z.com','sequoiacap.com','ycombinator.com','crunchbase.com','substack.com','bleepingcomputer.com','theregister.com','cnbc.com','businessinsider.com','finance.yahoo.com','economictimes.indiatimes.com','globeandmail.com','moneycontrol.com']"
```

**Search D — Gary Marcus 博客**:
```bash
timeout 60 kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search_advanced_exa: query='Gary Marcus AI', numResults=5, startPublishedDate='<startISO>', endPublishedDate='<endISO>', includeDomains=['techcrunch.com','theverge.com','wired.com','arstechnica.com','venturebeat.com','technologyreview.com','spectrum.ieee.org','reuters.com','bloomberg.com','ft.com','wsj.com','nytimes.com','fortune.com','foreignpolicy.com','36kr.com','jiqizhixin.com','leiphone.com','infoq.com','caixin.com','huxiu.com','anthropic.com','openai.com','deepmind.google','deepmind.com','research.google','blog.google','cloud.google.com','microsoft.com','azure.microsoft.com','techcommunity.microsoft.com','meta.com','ai.meta.com','engineering.fb.com','nvidia.com','developer.nvidia.com','aws.amazon.com','aboutamazon.com','apple.com','huggingface.co','mistral.ai','cohere.com','stability.ai','deepseek.com','xai.com','zhipuai.cn','moonshot.cn','minimax.io','salesforce.com','servicenow.com','palantir.com','databricks.com','snowflake.com','cerebras.net','groq.com','together.ai','pytorch.org','tensorflow.org','arxiv.org','openreview.net','acm.org','semanticscholar.org','kpmg.com','mckinsey.com','gartner.com','idc.com','forrester.com','shrm.org','semianalysis.com','stratechery.com','interconnects.ai','simonwillison.net','news.ycombinator.com','github.com','a16z.com','sequoiacap.com','ycombinator.com','crunchbase.com','substack.com','bleepingcomputer.com','theregister.com','cnbc.com','businessinsider.com','finance.yahoo.com','economictimes.indiatimes.com','globeandmail.com','moneycontrol.com']"
```

**Search E — AI Native 创业公司**:
```bash
timeout 60 kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search_advanced_exa: query='AI startup OR AI native OR YC AI OR seed round OR series A funding AI', numResults=15, startPublishedDate='<startISO>', endPublishedDate='<endISO>', includeDomains=['techcrunch.com','theverge.com','wired.com','arstechnica.com','venturebeat.com','technologyreview.com','spectrum.ieee.org','reuters.com','bloomberg.com','ft.com','wsj.com','nytimes.com','fortune.com','foreignpolicy.com','36kr.com','jiqizhixin.com','leiphone.com','infoq.com','caixin.com','huxiu.com','anthropic.com','openai.com','deepmind.google','deepmind.com','research.google','blog.google','cloud.google.com','microsoft.com','azure.microsoft.com','techcommunity.microsoft.com','meta.com','ai.meta.com','engineering.fb.com','nvidia.com','developer.nvidia.com','aws.amazon.com','aboutamazon.com','apple.com','huggingface.co','mistral.ai','cohere.com','stability.ai','deepseek.com','xai.com','zhipuai.cn','moonshot.cn','minimax.io','salesforce.com','servicenow.com','palantir.com','databricks.com','snowflake.com','cerebras.net','groq.com','together.ai','pytorch.org','tensorflow.org','arxiv.org','openreview.net','acm.org','semanticscholar.org','kpmg.com','mckinsey.com','gartner.com','idc.com','forrester.com','shrm.org','semianalysis.com','stratechery.com','interconnects.ai','simonwillison.net','news.ycombinator.com','github.com','a16z.com','sequoiacap.com','ycombinator.com','crunchbase.com','substack.com','bleepingcomputer.com','theregister.com','cnbc.com','businessinsider.com','finance.yahoo.com','economictimes.indiatimes.com','globeandmail.com','moneycontrol.com']"
```

**Search F — AWS Cloud**:
```bash
timeout 60 kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search_advanced_exa: query='AWS OR Amazon Web Services OR Bedrock OR SageMaker OR AWS AI', numResults=15, startPublishedDate='<startISO>', endPublishedDate='<endISO>', includeDomains=['techcrunch.com','theverge.com','wired.com','arstechnica.com','venturebeat.com','technologyreview.com','spectrum.ieee.org','reuters.com','bloomberg.com','ft.com','wsj.com','nytimes.com','fortune.com','foreignpolicy.com','36kr.com','jiqizhixin.com','leiphone.com','infoq.com','caixin.com','huxiu.com','anthropic.com','openai.com','deepmind.google','deepmind.com','research.google','blog.google','cloud.google.com','microsoft.com','azure.microsoft.com','techcommunity.microsoft.com','meta.com','ai.meta.com','engineering.fb.com','nvidia.com','developer.nvidia.com','aws.amazon.com','aboutamazon.com','apple.com','huggingface.co','mistral.ai','cohere.com','stability.ai','deepseek.com','xai.com','zhipuai.cn','moonshot.cn','minimax.io','salesforce.com','servicenow.com','palantir.com','databricks.com','snowflake.com','cerebras.net','groq.com','together.ai','pytorch.org','tensorflow.org','arxiv.org','openreview.net','acm.org','semanticscholar.org','kpmg.com','mckinsey.com','gartner.com','idc.com','forrester.com','shrm.org','semianalysis.com','stratechery.com','interconnects.ai','simonwillison.net','news.ycombinator.com','github.com','a16z.com','sequoiacap.com','ycombinator.com','crunchbase.com','substack.com','bleepingcomputer.com','theregister.com','cnbc.com','businessinsider.com','finance.yahoo.com','economictimes.indiatimes.com','globeandmail.com','moneycontrol.com']"
```

**Search G — Anthropic 专项**:
```bash
timeout 60 kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search_advanced_exa: query='Anthropic OR Claude OR Claude Code OR MCP Model Context Protocol', numResults=15, startPublishedDate='<startISO>', endPublishedDate='<endISO>', includeDomains=['techcrunch.com','theverge.com','wired.com','arstechnica.com','venturebeat.com','technologyreview.com','spectrum.ieee.org','reuters.com','bloomberg.com','ft.com','wsj.com','nytimes.com','fortune.com','foreignpolicy.com','36kr.com','jiqizhixin.com','leiphone.com','infoq.com','caixin.com','huxiu.com','anthropic.com','openai.com','deepmind.google','deepmind.com','research.google','blog.google','cloud.google.com','microsoft.com','azure.microsoft.com','techcommunity.microsoft.com','meta.com','ai.meta.com','engineering.fb.com','nvidia.com','developer.nvidia.com','aws.amazon.com','aboutamazon.com','apple.com','huggingface.co','mistral.ai','cohere.com','stability.ai','deepseek.com','xai.com','zhipuai.cn','moonshot.cn','minimax.io','salesforce.com','servicenow.com','palantir.com','databricks.com','snowflake.com','cerebras.net','groq.com','together.ai','pytorch.org','tensorflow.org','arxiv.org','openreview.net','acm.org','semanticscholar.org','kpmg.com','mckinsey.com','gartner.com','idc.com','forrester.com','shrm.org','semianalysis.com','stratechery.com','interconnects.ai','simonwillison.net','news.ycombinator.com','github.com','a16z.com','sequoiacap.com','ycombinator.com','crunchbase.com','substack.com','bleepingcomputer.com','theregister.com','cnbc.com','businessinsider.com','finance.yahoo.com','economictimes.indiatimes.com','globeandmail.com','moneycontrol.com']"
```

> `<startISO>` 和 `<endISO>` 为占位符，执行时由 Agent 根据 Step 0 计算结果替换。

### Step 3: 按六大主题分类

将搜索结果按 `topics-definition.md` 中的匹配规则分类：
1. 精确匹配: 直接包含关键词 → 归入对应主题
2. 语义匹配: 根据内容判断最相关主题
3. 多主题: 一条新闻可归入多个主题（交叉标注）
4. 未分类: 不符合六大主题 → "其他/Misc"

### Step 4: 写入日报（增量追加）

输出文件: `output/YYYY-MM-DD.md`（日期使用 UTC+8 北京时间）

**条目字段说明**：
- `来源`: 报道该事件的媒体/网站域名（必须是白名单域名，不得填"技术媒体"等模糊描述）
- `时间`: 文章/报道的发布时间（YYYY-MM-DD 或 YYYY-MM-DDTHH:MM UTC 格式）
- `事件时间`: **核心事件实际发生的时间**（非文章发布时间）
  - 产品发布 → 发布会/公告日期
  - 融资事件 → 交割/披露日期
  - 裁员 → 裁员通知/生效日期
  - 研究报告 → 报告正式发布日期
  - 无法确定时 → 填 `近期`（系统将视为今天）
  - ⚠️ **绝不可用文章发布时间代替事件时间**——如果一篇今天的分析文章讨论 14 个月前的事件，事件时间应填 14 个月前的日期
- `链接`: **必填，必须是真实 https:// URL**
  - ❌ 禁止填写：`（多来源报道）`、`(via Exa Search A)`、`（推断可信）`等文字说明
  - ✅ 正确做法：从 Exa 搜索结果中取最权威来源的 URL（官方博客 > TechCrunch > 其他白名单来源）
  - 如果同一事件有多个来源，选最权威的一个，其余在摘要中提及
  - **没有真实 URL 的条目不得写入日报**（写作系统依赖 URL 抓取全文验证事件时间）

**文件不存在时（当天首次运行）→ 创建新文件**：

```markdown
# Tech Updates - YYYY-MM-DD

**创建时间**: YYYY-MM-DD HH:MM UTC+8
**来源**: Twitter/X, 博客, 技术媒体 (via Exa MCP)
**采集模式**: 增量追加

---

## 📚 主题索引
（每次追加时更新此区域）

---

## 🕐 采集批次 #1 (HH:MM UTC+8)
**搜索窗口**: startISO → endISO
**本批新增**: N 条

### 🤖 openclaw
#### 1. [标题]
- 来源: [来源名称，如 TechCrunch / Anthropic 官博]
- 时间: [文章/报道发布时间，格式 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM UTC]
- 事件时间: [核心事件实际发生时间，格式 YYYY-MM-DD 或 YYYY-MM；无法确定时填"近期"]
- 摘要: ...
- 关键词: #agent #autonomous
- 链接: https://...（必填！每条必须提供至少一个真实可访问的 URL）

> ⚠️ **链接字段强制要求**：
> - 每条条目的「链接」字段必须是真实的 `https://` URL，不得填写"（多来源报道）"、"(via Exa Search X)"、"（推断可信）"等文字说明
> - 如果 Exa 搜索返回了多个来源，选择最权威的一个 URL 填入「链接」字段
> - 如果确实找不到直接 URL（如 Twitter/X 帖子已删除），使用最相关的权威报道 URL
> - 没有真实 URL 的条目**不得写入日报**（写作系统无法 web fetch 验证事件时间）

### 🏢 ai-org-structure
（以此类推各主题...）

### 📊 本批统计
- 新增更新数: N 条
- 主题分布: openclaw X, ai-org-structure Y, ...
```

**文件已存在时（当天后续运行）→ 追加新批次**：

```markdown

---

## 🕐 采集批次 #N (HH:MM UTC+8)
**搜索窗口**: startISO → endISO
**本批新增**: N 条

### 🤖 openclaw
（新内容...）

### 📊 本批统计
- 新增更新数: N 条
- 主题分布: ...
```

同时更新文件顶部的**主题索引**（累计总数）和**最后更新**时间行（格式：`YYYY-MM-DD HH:MM UTC+8（第N批）`）。

**去重规则**：追加前检查新结果的 URL 是否已存在于当天文件中，跳过重复项。

### Step 5: 更新状态

更新 `state.json`：

```json
{
  "lastCollectorCheck": <当前 Unix 时间戳>,
  "todayFile": "output/YYYY-MM-DD.md",
  "todayBatchCount": <当天已执行的批次数>,
  "todayTotalItems": <当天累计条目数>
}
```

### Step 6: 通知

**当天首次采集**：
1. 发送飞书消息摘要（各主题亮点）
2. 发送 markdown 文件附件（`output/YYYY-MM-DD.md`）
3. 创建飞书文档（`feishu_doc create`，归入 AI Daily Report 文件夹 `L3V1fJHAQlK7sUdy1r3cuRFhn8b`），写入完整日报内容
4. 发送飞书文档链接

**后续增量采集**：
- 如果新增 ≥ 5 条 → 发飞书消息通知（摘要 + 文件链接），并追加到当天飞书文档
- 如果新增 < 5 条 → 静默追加，不打扰用户
- 如果新增 0 条 → 不通知
- ⚠️ **追加飞书文档时必须同时更新头部信息**：
  - 文档标题更新为：`AI 日报 YYYY-MM-DD（N条 · M批次）`
  - 头部「最后更新」行更新为当前批次时间
  - 主题索引更新为累计总数
  - 使用 `feishu_doc write` 全量覆盖头部 + 索引区域（因 `feishu_doc` 没有 block 级编辑能力，追加内容时需先读取文档全文、修改头部、再全量写回；或分两步：先 append 新批次内容，再用 `update_block` 更新标题 block）

## State

文件: `state.json`

```json
{
  "lastCollectorCheck": 0,
  "todayFile": null,
  "todayBatchCount": 0,
  "todayTotalItems": 0
}
```

| 字段 | 说明 |
|------|------|
| `lastCollectorCheck` | 上次采集完成的 Unix 时间戳 |
| `todayFile` | 当天日报文件路径（UTC+8 日期） |
| `todayBatchCount` | 当天已执行的采集批次数 |
| `todayTotalItems` | 当天累计采集条目总数 |

## Output

日报文件存放在 `output/` 目录:
```
output/
├── 2026-03-16.md
├── 2026-03-17.md     ← 可能包含多个采集批次
├── 2026-03-18.md
└── ...
```

每个文件内部按采集批次时序排列，每个批次独立标注搜索窗口和统计。

## 日期边界处理

- 日期以 **UTC+8（北京时间）** 为准
- 跨天判断：如果当前 UTC+8 日期 ≠ `todayFile` 中的日期 → 创建新文件，重置 `todayBatchCount` 和 `todayTotalItems`
- 示例：UTC 16:00（北京 00:00）时切换到新一天的日报文件

## Troubleshooting

| 问题 | 处理 |
|------|------|
| kiro-cli 未安装 | `kiro-cli auth status` 检查，参考 `3. KiroCLI/kiro_install_config.md` |
| Exa 搜索无结果 | 检查 `~/.kiro/settings/mcp.json` 中 exa 配置 |
| 搜索超时 | 拆分为更小的查询批次；检查网络连接 |
| 日报格式异常 | 参考 `output/` 中的历史日报样例 |
| 增量窗口过短无结果 | 正常现象，静默跳过即可 |
| state.json 损坏 | 删除后重新创建，首次运行将全量搜 24h |
