# Tech Updates Collector — OpenClaw 安装配置指南

> 本文档供 OpenClaw Agent 读取并在宿主机上执行，完成 tech-updates-collector Skill 的安装与配置。
>
> 幂等性原则：所有操作执行前先检查当前状态，已存在的配置只验证不重复写入，重复执行不会产生副作用。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档所有章节，理解：
- 目标：安装 `tech-updates-collector` Skill，配置 Cron 定时采集任务
- 核心依赖：Kiro CLI（已安装且登录）+ Exa MCP Server（已配置在 `~/.kiro/settings/mcp.json`）
- Skill 文件位置：`~/openclaw/skills/tech-updates-collector/`（或实际 OpenClaw 工作目录下）
- 最终验收标准：Skill 文件就位、依赖可用、Cron Job 已配置（或 HEARTBEAT.md 已包含采集任务段落）

### 第二步：检查当前环境状态

通读完成后，先执行以下诊断命令，收集当前状态：

```bash
# 1. OpenClaw 工作目录（取实际路径，以下用 $OC_DIR 代替）
OC_DIR="$HOME/.openclaw"
echo "OpenClaw 工作目录: $OC_DIR"

# 2. Skill 是否已安装
ls "$OC_DIR/skills/tech-updates-collector/SKILL.md" 2>/dev/null \
  && echo "SKILL_INSTALLED" || echo "SKILL_NOT_INSTALLED"

# 3. topics-definition.md 是否存在
ls "$OC_DIR/skills/tech-updates-collector/topics-definition.md" 2>/dev/null \
  && echo "TOPICS_DEF_EXISTS" || echo "TOPICS_DEF_MISSING"

# 4. state.json 是否存在且合法
python3 -c "
import json, os
p = os.path.expanduser('$OC_DIR/skills/tech-updates-collector/state.json')
d = json.load(open(p))
print(f'STATE_OK lastCollectorCheck={d.get(\"lastCollectorCheck\", \"MISSING\")} todayFile={d.get(\"todayFile\", \"MISSING\")} batchCount={d.get(\"todayBatchCount\", \"MISSING\")} totalItems={d.get(\"todayTotalItems\", \"MISSING\")}')
" 2>/dev/null || echo "STATE_JSON_INVALID_OR_MISSING"

# 5. output 目录是否存在
ls "$OC_DIR/skills/tech-updates-collector/output/" 2>/dev/null \
  && echo "OUTPUT_DIR_EXISTS" || echo "OUTPUT_DIR_MISSING"

# 6. Kiro CLI 是否可用
kiro-cli --version 2>/dev/null || echo "KIRO_CLI_NOT_FOUND"
kiro-cli auth status 2>/dev/null || echo "KIRO_AUTH_UNKNOWN"

# 7. Exa MCP 是否已配置
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.kiro/settings/mcp.json')))
servers = cfg.get('mcpServers', {})
exa = servers.get('exa', {})
if exa:
    if 'url' in exa:
        url = exa['url']
        has_key = 'exaApiKey=' in url and 'exaApiKey=<' not in url
        has_tools = 'tools=' in url
        print(f'EXA_CONFIGURED=remote url_mode key={has_key} tools_param={has_tools}')
        if has_tools and 'web_search_advanced_exa' in url:
            print('EXA_ADVANCED_SEARCH=available')
        else:
            print('EXA_ADVANCED_SEARCH=missing_or_default')
    elif 'command' in exa:
        print('EXA_CONFIGURED=local_npx (⚠️ 不推荐，v3.1.9+ 仅暴露 2 个工具)')
    else:
        print('EXA_CONFIGURED=unknown_format')
else:
    print('EXA_NOT_CONFIGURED')
" 2>/dev/null || echo "MCP_CONFIG_READ_FAILED"

# 8. Cron Job 是否已配置
OPENCLAW_GATEWAY_PORT=18789 OPENCLAW_GATEWAY_TOKEN=<token> openclaw cron list 2>/dev/null | grep -q "a061691d" \
  && echo "CRON_JOB_CONFIGURED" || echo "CRON_JOB_NOT_FOUND"

# 9. HEARTBEAT.md 中是否有采集任务（旧模式，已迁移到 Cron）
grep -c "Tech Updates 采集" "$OC_DIR/HEARTBEAT.md" 2>/dev/null || echo "HEARTBEAT_TASK_NOT_FOUND"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应文档 | 前置条件 | 需要用户确认的情况 |
|------|----------|----------|-------------------|
| 阶段 1：依赖检查 | 第 3 节 | 无 | Kiro CLI 未安装/未登录时暂停；Exa MCP 未配置时暂停，引导参考 `3. KiroCLI/kiro_mcp_recommended.md` |
| 阶段 2：安装 Skill 文件 | 第 4 节 Step 1-4 | 阶段 1 通过 | Skill 目录已存在时跳过复制，仅验证文件完整性 |
| 阶段 3：配置 Cron 调度 | 第 5 节 | 阶段 2 完成 | Cron Job 已存在时跳过；确认 Cron Job ID 和执行时间 |
| 阶段 4：端到端验证 | 第 6-7 节 | 阶段 3 完成 | 验证失败时展示错误并等待用户决策 |

### 执行原则

1. **先诊断，后执行** — 不要跳过状态检查直接复制文件或修改配置
2. **幂等性优先** — Skill 目录已存在时不覆盖，Cron Job 已存在时不重复创建
3. **遇到异常立即暂停** — 依赖缺失、文件权限不足等情况，停下来向用户说明
4. **每阶段汇报** — 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续
5. **已完成的步骤可跳过** — 如果诊断发现 Skill 已安装且文件完整，直接标记 ✅ 跳过

---

## 1. Skill 简介

`tech-updates-collector` 是一个 AI 资讯采集 Skill，按六大主题从 Twitter/X、博客、技术媒体等来源自动采集最新 AI 资讯，生成结构化日报。

**输入**：时间窗口（`lastCollectorCheck` → 当前时间，最长 24 小时）。

**输出**：`output/YYYY-MM-DD.md`，结构化 Markdown 日报，按六大主题分区，多次采集按批次追加。

**核心价值**：每日六次定时采集全球 AI 动态，覆盖模型发布、融资、企业应用、组织变革等关键维度，为 [tech-updates-writer](../tech-updates-writer/SKILL.md) 写作系统提供高质量素材输入。增量模式保证每批只处理新内容，避免重复，同时白名单机制确保来源可信度。

搜索能力通过宿主机上的 Kiro CLI 调用 Exa MCP Server 实现（远程 URL 模式，工具名带 `_exa` 后缀）。推荐使用 `web_search_advanced_exa` 的日期过滤功能，配合增量搜索窗口（`lastCheck → now`）精确限制采集范围，避免重复搜索。

---

## 2. 系统架构

### 采集流程

```
Step 0: 计算搜索时间窗口
        ├── 读取 state.json → lastCollectorCheck
        ├── 首次/超24h → 搜最近 24 小时
        └── 常规 → lastCheck → now（增量）

Step 1: 检查执行条件
        └── 距上次执行 < 3 小时 → 跳过

Step 2: 执行搜索（串行，防 OOM）
        ├── Dimension A: 通用 AI/科技动态
        ├── Dimension B: 行业领袖动态
        ├── Dimension C: 企业 AI 产品
        ├── Dimension D: AI 批评性视角（Gary Marcus）
        ├── Dimension E: AI Native 创业与融资
        ├── Dimension F: AWS 云服务生态
        └── Dimension G: Anthropic 专项追踪
           （通过 kiro-cli → Exa MCP，每个维度 timeout 60s，失败跳过）

Step 3: 按六大主题分类
        └── 精确匹配 → 语义匹配 → 多主题交叉标注 → Misc

Step 4: 写入日报（增量追加）
        ├── 首次运行当天 → 创建新文件
        └── 后续运行 → 追加新批次，更新主题索引

Step 5: 更新 state.json
Step 6: 发送飞书通知（首次采集/新增 ≥ 5 条时）
```

### 六大主题

| # | 标识符 | 主题名称 | 核心关注点 |
|---|--------|----------|------------|
| 1 | 🤖 `openclaw` | AI Agent 能力与平台 | Agent 技术、自主化、工具使用、Agent 框架 |
| 2 | 🏢 `ai-org-structure` | AI 时代的组织变革 | 裁员、组织重构、岗位演变、工作流程自动化 |
| 3 | 💼 `agentic-cases` | AI Agent 实战案例 | 落地案例、ROI 验证、AI Native 创业公司 |
| 4 | 🛒 `agentic-commerce` | AI 商业应用 | 电商、营销自动化、客服、个性化推荐 |
| 5 | 🏭 `enterprise-ai` | 企业 AI 应用 | 企业级产品、B2B SaaS、企业采购决策 |
| 6 | ⚙️ `ai-dlc` | AI 开发生命周期 | MLOps/LLMOps、AI Coding、模型训练部署、AI 基础设施 |

> 详细关键词与匹配规则见 [`topics-definition.md`](./topics-definition.md)（Single Source of Truth）。

### 与写作系统的关系

```
tech-updates-collector               tech-updates-writer
─────────────────────                ─────────────────────

每日 6 次采集 →  output/YYYY-MM-DD.md  →  Orchestrator 消费
                 （增量追加，多批次）        （Phase 0 读取日报）
                                            ↓
                                     生成多篇结构化文章
                                     发布到微信/飞书等渠道
```

**消费机制**：

- 写作系统在北京时间 **15:00+** 由心跳触发，读取当天最新日报
- 日报文件路径由 `state.json → todayFile` 字段指向
- 写作系统依赖日报中每条条目的 **`链接`** 字段（真实 `https://` URL）进行全文抓取和事件时间验证
- 若当天日报尚未采集完毕，写作系统读取已有批次内容，不阻塞

---

## 3. 目录结构

```
skills/tech-updates-collector/
├── SKILL.md                 # Skill 定义（触发条件、搜索策略、输出格式）
├── topics-definition.md     # 六大主题权威定义（Single Source of Truth）
├── state.json               # 采集状态 {"lastCollectorCheck", "todayFile", "todayBatchCount", "todayTotalItems"}
└── output/                  # 日报输出目录（每日一个文件，增量追加去重）
    └── 2026-03-16.md        # 历史日报样例（多次采集的累积结果）
```

---

## 4. 依赖条件

### 4.1 Kiro CLI（必需）

Kiro CLI 必须安装在 OpenClaw 同一台宿主机上，并已登录。

```bash
# 检查安装
kiro-cli --version

# 检查登录状态
kiro-cli auth status
```

如未安装，参考 `3. KiroCLI/kiro_install_config.md`。

### 4.2 Exa MCP Server（必需）

Kiro CLI 的 MCP 配置中必须包含 Exa Search Server。

> ⚠️ **重要变更**：`exa-mcp-server` npm 本地包（v3.1.9+）已不再支持 `--tools` 参数，仅暴露 2 个默认工具。**推荐使用远程 URL 模式**，可获得完整的 5 个工具，且工具名带 `_exa` 后缀。

检查配置文件 `~/.kiro/settings/mcp.json`，确认存在 `exa` 相关条目。

**推荐配置 — 远程 URL 模式（带 API Key）：**

```json
{
  "mcpServers": {
    "exa": {
      "url": "https://mcp.exa.ai/mcp?exaApiKey=<your-api-key>&tools=web_search_exa,web_search_advanced_exa,company_research_exa,crawling_exa,people_search_exa"
    }
  }
}
```

**远程模式可用工具：**

| 工具名 | 说明 | 采集价值 |
|--------|------|----------|
| `web_search_exa` | 通用网页搜索 | 博客、新闻 |
| `web_search_advanced_exa` | 高级搜索，支持 `startPublishedDate` / `endPublishedDate` 日期过滤 | ✅ 精确限制采集窗口 |
| `company_research_exa` | 公司研究 | 企业 AI 动态 |
| `crawling_exa` | 网页内容抓取 | 深度阅读原文 |
| `people_search_exa` | 人物搜索 | AI 领域关键人物 |

> `web_search_advanced_exa` 的日期过滤能力对日报采集至关重要 — 可以精确限制搜索窗口，避免重复采集旧资讯。

**无 API Key 时的备选 — 远程免 Key 模式：**

```json
{
  "mcpServers": {
    "exa": {
      "url": "https://mcp.exa.ai/mcp"
    }
  }
}
```

> 免 Key 模式有调用频率限制，适合验证配置。生产采集建议使用带 API Key 的模式。
> 获取 API Key: [https://dashboard.exa.ai/api-keys](https://dashboard.exa.ai/api-keys)

**⚠️ 不推荐 — 本地 npx 模式（已过时）：**

```
# exa-mcp-server@3.1.9+ 的 npx 模式忽略 --tools 参数，
# 仅暴露 web_search_exa 和 get_code_context_exa 两个工具，
# 缺少 web_search_advanced_exa（日期过滤）、crawling_exa 等关键工具。
# 请勿使用此模式。
```

验证 Exa MCP 可用：

```bash
kiro-cli chat --no-interactive --trust-all-tools "use web_search_exa to search for: test query"
```

### 4.3 Python 3（可选）

用于处理 JSON 输出、时间计算等辅助任务：

```bash
python3 --version
```

### 4.4 LiteLLM（可选）

用于本地 LLM 辅助分类（如已配置）：

```bash
litellm --version
```

---

## 5. 搜索配置

### 搜索命令（A-G）

7 个搜索维度串行执行（防 OOM，c7g.large 仅 3.7GB RAM），每个命令加 `timeout 60` 前缀：

| 维度 | 名称 | 核心关键词 | numResults |
|------|------|------------|------------|
| **A** | 通用 AI/科技动态 | AI, GenAI, Anthropic, Claude, OpenAI, DeepSeek, semiconductors, layoffs | 20 |
| **B** | 行业领袖动态 | Sam Altman, Elon Musk, Satya Nadella, Sundar Pichai, Andrej Karpathy, Yann LeCun | 15 |
| **C** | 企业 AI 产品 | Palantir, Salesforce, ServiceNow, Workday, Agentforce enterprise AI | 15 |
| **D** | AI 批评性视角 | Gary Marcus AI（仅 garymarcus.substack.com 等来源） | 5 |
| **E** | AI Native 创业与融资 | AI startup, AI native, YC AI, seed round, series A funding AI | 15 |
| **F** | AWS 云服务生态 | AWS, Amazon Web Services, Bedrock, SageMaker, AWS AI | 15 |
| **G** | Anthropic 专项追踪 | Anthropic, Claude, Claude Code, MCP Model Context Protocol | 15 |

所有搜索使用 Step 0 计算的 `startISO`/`endISO` 时间窗口，通过 `web_search_advanced_exa` 的 `startPublishedDate`/`endPublishedDate` 参数传入。

### 白名单来源

所有 Exa 搜索通过 `includeDomains` 参数**强制限定白名单域名**，白名单外结果一律不采纳：

| 层级 | 来源类型 | 代表域名 | 优先级 |
|------|----------|----------|--------|
| **Tier 1** | 顶级科技媒体 | techcrunch.com, theverge.com, reuters.com, bloomberg.com | 高 |
| **Tier 1（中文）** | 中文科技媒体 | 36kr.com, jiqizhixin.com, huxiu.com | 高 |
| **Tier 2** | 公司官方博客/主站 | anthropic.com, openai.com, nvidia.com, aws.amazon.com | **最高（发布即事实）** |
| **Tier 2** | 学术/研究机构 | arxiv.org, mckinsey.com, gartner.com | 高 |
| **Tier 3** | 高质量专业博客 | semianalysis.com, simonwillison.net, news.ycombinator.com | 中高 |
| **Tier 4** | 补充来源 | cnbc.com, businessinsider.com, theregister.com | 中 |

**选取原则**：同一事件有多个来源时，选最权威的一个 URL 填入 `链接` 字段——官方博客 > TechCrunch > 其他白名单来源。

完整白名单列表见 `SKILL.md` 中的 `includeDomains` 域名集合。

---

## 6. 安装步骤

### Step 1: 复制 Skill 到 OpenClaw skills 目录

先检查 Skill 是否已安装：

```bash
OC_SKILL_DIR="$HOME/.openclaw/skills/tech-updates-collector"
if [ -f "$OC_SKILL_DIR/SKILL.md" ]; then
  echo "✔ tech-updates-collector Skill 已安装，跳过复制"
else
  echo "安装 tech-updates-collector Skill..."
  cp -r skills/tech-updates-collector "$OC_SKILL_DIR"
  echo "✔ Skill 已复制到 $OC_SKILL_DIR"
fi
```

### Step 2: 验证 topics-definition.md

确认 `topics-definition.md` 中的六大主题定义符合当前需求。如需调整主题或关键词，只需修改此文件（唯一维护点）。

### Step 3: 初始化 state.json

首次安装时 `state.json` 已初始化为 `{"lastCollectorCheck": 0}`，Agent 首次执行时会立即触发采集。

### Step 4: 验证 output 目录

```bash
ls skills/tech-updates-collector/output/
# 应看到历史日报文件，如 2026-03-16.md
```

---

## 7. Cron 调度配置

> **2026-03-23 变更**：采集任务已从 HEARTBEAT.md 迁移到 OpenClaw Cron 独立调度。

| 属性 | 值 |
|------|----|
| Cron Job ID | `a061691d-99b9-40ca-bbf0-ac353cbd64f9` |
| 执行时间（北京时间） | 07:00 / 10:00 / 13:00 / 16:00 / 19:00 / 22:00（每日 6 次） |
| 隔离模式 | 独立 session，不影响主会话 context |

```bash
# 查看 Cron 状态
OPENCLAW_GATEWAY_PORT=18789 OPENCLAW_GATEWAY_TOKEN=<token> openclaw cron list
```

**迁移原因**：独立 Cron 能精确控制执行时间，隔离 context 消耗，主会话不受采集任务干扰。

### HEARTBEAT.md 兼容（旧模式）

如果 Cron 尚未配置，可在 HEARTBEAT.md 中保留采集任务段落作为兜底。先检查是否已存在：

```bash
HEARTBEAT_FILE="$HOME/.openclaw/HEARTBEAT.md"
if grep -q "Tech Updates 采集" "$HEARTBEAT_FILE" 2>/dev/null; then
  echo "✔ Tech Updates 采集任务已存在，跳过写入"
else
  cat >> "$HEARTBEAT_FILE" << 'EOF'

## Tech Updates 采集 📰 (every 1+ hour)
If 1+ hour since last check (see `skills/tech-updates-collector/state.json` → `lastCollectorCheck`):
- 参考 `skills/tech-updates-collector/SKILL.md` 执行采集流程
- 通过 kiro-cli 调用 Exa MCP 工具搜索 AI 资讯
- 搜索窗口：增量模式（lastCheck → now），首次/宕机恢复兜底 24h
- 优先使用 `web_search_advanced_exa` 精确限制搜索时间范围
- 按六大主题分类，增量追加去重写入日报: `skills/tech-updates-collector/output/YYYY-MM-DD.md`
- 更新 `skills/tech-updates-collector/state.json`（时间戳 + 批次计数 + 条目总数）
- 分级通知：首次采集发完整日报，增量 ≥5 条发摘要，<5 条静默，0 条不通知
EOF
  echo "✔ Tech Updates 采集任务已写入 $HEARTBEAT_FILE"
fi
```

---

## 8. 输出格式规范

### 日报 Markdown 结构

```markdown
# Tech Updates - YYYY-MM-DD

**创建时间**: YYYY-MM-DD HH:MM UTC+8
**采集模式**: 增量追加

---

## 📚 主题索引（累计总数，每批更新）

---

## 🕐 采集批次 #N (HH:MM UTC+8)
**搜索窗口**: startISO → endISO
**本批新增**: N 条

### 🤖 openclaw
#### 1. [标题]
- 来源: [白名单域名，如 TechCrunch / Anthropic 官博]
- 时间: [文章发布时间，YYYY-MM-DD]
- 事件时间: [核心事件实际发生时间，无法确定填"近期"]
- 摘要: ...
- 关键词: #agent #autonomous
- 链接: https://...（必填！真实 URL）

### 📊 本批统计
```

### 字段说明

| 字段 | 说明 | 格式要求 |
|------|------|----------|
| `来源` | 报道该事件的媒体/网站 | 必须是白名单域名，不得填"技术媒体"等模糊描述 |
| `时间` | 文章/报道发布时间 | `YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM UTC` |
| `事件时间` | **核心事件实际发生时间**（非文章时间） | `YYYY-MM-DD` / `YYYY-MM`；无法确定填 `近期` |
| `链接` | 事件来源 URL | **必填**，必须是真实 `https://` URL（2026-04-06 强制） |

> ⚠️ **链接字段强制要求**（2026-04-06 新增）：禁止填写"（多来源报道）"、"(via Exa Search A)"等文字说明。没有真实 URL 的条目不得写入日报——写作系统依赖 URL 进行全文抓取验证。

### 输出文件

- **位置**：`output/YYYY-MM-DD.md`（日期以 UTC+8 北京时间为准）
- **格式**：增量追加批次，每批含独立的时间戳、搜索窗口、统计和六大主题分区
- **链接字段**：必须是真实 `https://` URL（2026-04-06 新增强制要求，无 URL 条目不得写入）
- **去重机制**：追加前检查新结果 URL 是否已存在于当天文件，跳过重复项
- **跨天处理**：当北京时间日期变化时，创建新文件，重置批次计数

```
output/
├── 2026-04-04.md
├── 2026-04-05.md     ← 每天一文件，多批次追加
├── 2026-04-06.md
└── ...
```

### state.json 结构

文件路径：`~/.openclaw/workspace/output/state.json`（或 Skill 工作目录下）

```json
{
  "lastCollectorCheck": 1712345678,
  "todayFile": "output/2026-04-06.md",
  "todayBatchCount": 3,
  "todayTotalItems": 47
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `lastCollectorCheck` | Unix 时间戳 | 上次采集完成时间，用于计算增量窗口 |
| `todayFile` | 字符串 | 当天日报文件路径（UTC+8 日期） |
| `todayBatchCount` | 整数 | 当天已执行的采集批次数 |
| `todayTotalItems` | 整数 | 当天累计采集条目总数 |

---

## 9. 工作流概览

```
Cron Job 触发（北京时间 07/10/13/16/19/22:00）
  → Agent 读取 SKILL.md
  → 检查 state.json（是否需要执行，距上次 < 3h → 跳过）
  → 计算搜索窗口（增量: lastCheck → now，兜底: now-24h → now）
  → 按 7 组搜索维度（A-G）串行调用 kiro-cli → Exa MCP
    （使用 web_search_advanced_exa 限制时间窗口，每维度 timeout 60s）
  → 搜索结果按 topics-definition.md 六大主题分类
    （精确匹配 → 语义匹配 → 多主题交叉标注 → Misc）
  → 增量追加去重写入 output/YYYY-MM-DD.md
    （首次创建新文件；后续执行按 URL 去重，仅追加新条目）
  → 更新主题索引和批次统计
  → 更新 state.json（时间戳 + todayFile + batchCount + totalItems）
  → 分级通知（首次→完整日报，≥5条→摘要，<5条→静默，0条→不通知）
  → 发送飞书通知（首次采集/新增 ≥ 5 条时）
```

---

## 10. 运行要求

| 依赖 | 说明 | 验证命令 |
|------|------|----------|
| **kiro-cli** | 调用 Exa MCP Server 的核心工具 | `kiro-cli auth status` |
| **Exa MCP Server** | 实际执行 web 搜索 | 检查 `~/.kiro/settings/mcp.json` 中 `exa` 条目 |
| **Python 3** | 处理 JSON 输出、时间计算 | `python3 --version` |
| **LiteLLM**（可选） | 用于本地 LLM 辅助分类（如已配置） | `litellm --version` |

---

## 11. 已知限制 / 待改进

| # | 问题 | 说明 |
|---|------|------|
| 1 | 「事件时间」字段准确性 | Exa 返回的是文章发布时间，Agent 需通过摘要内容推断核心事件实际发生时间，存在误判风险；无法确定时填 `近期`（写作系统将视为今日） |
| 2 | Twitter/X 实时覆盖 | Exa 的 Twitter 搜索覆盖率有限，行业领袖的实时推文不总能被捕获；高影响力推文可能延迟 1-2 天才出现在 Web 收录中 |
| 3 | 中文媒体覆盖率 | 36kr、极客公园等中文来源搜索召回率低于英文媒体；中文独家报道存在遗漏风险 |
| 4 | Dimension D（Gary Marcus）覆盖 | 目前仅通过白名单中 `substack.com` 间接搜索，若 Gary Marcus 发文不触发 Exa 收录，可能漏采 |
| 5 | 串行执行效率 | 7 个维度串行以防 OOM，总采集时间约 5-10 分钟；硬件升级后可考虑部分并行 |
| 6 | 白名单时效性 | 白名单域名需人工维护，新兴可信来源需手动添加；投资分析类垃圾来源偶尔绕过 Tier 4 白名单混入 |

---

## 12. 常见问题

| 问题 | 排查方法 |
|------|----------|
| kiro-cli 未安装 | `kiro-cli --version`，参考安装文档 |
| Exa 搜索无结果 | 检查 `~/.kiro/settings/mcp.json` 中 Exa 配置；确认使用远程 URL 模式而非本地 npx |
| Exa 只有 2 个工具 | 本地 npx 模式（v3.1.9+）已不支持 `--tools` 参数，切换到远程 URL 模式 |
| 工具名报错 (twitter_search 不存在) | 远程 URL 模式工具名带 `_exa` 后缀：`twitter_search_exa`、`web_search_advanced_exa` |
| 缺少日期过滤能力 | 确认远程 URL 中包含 `web_search_advanced_exa` 工具 |
| 搜索超时 | 拆分为更小的查询批次；检查网络连接；每维度 timeout 60s，失败跳过 |
| 日报格式异常 | 参考 `output/2026-03-16.md` 样例对比 |
| 日报条目重复 | 检查去重逻辑是否按 URL 精确匹配；确认未手动修改条目链接 |
| 多次执行后条目序号不连续 | 正常现象 — 新条目序号接续该主题已有最大序号，不会重新编号 |
| state.json 时间戳不更新 | 检查 Agent 是否有文件写入权限 |
| 每次都搜 24h 没有增量效果 | 检查 `state.json` 的 `lastCollectorCheck` 是否正常更新；值为 0 或过期 >24h 会触发兜底全量搜索 |
| 出现 YYYY-MM-DD-evening.md 等异常文件名 | 日报文件名必须严格为 `YYYY-MM-DD.md`，不允许后缀变体；删除异常文件 |
| 通知过于频繁 | 分级通知：增量 <5 条应静默追加，0 条不通知；检查 SKILL.md Step 5 通知策略 |
| 链接字段填了非 URL 文字 | 2026-04-06 起强制要求真实 `https://` URL，无 URL 条目不得写入日报 |

---

## 13. 更新历史

| 日期 | 变更内容 |
|------|----------|
| **2026-04-06** | 新增「链接字段强制要求」：禁止非 URL 文字填入链接字段，无 URL 条目不得写入日报 |
| **2026-04-04** | 新增 **Dimension G**（Anthropic 专项追踪），独立追踪 Anthropic/Claude 最新动态 |
| **2026-03-23** | 采集任务从 HEARTBEAT.md 迁移至 **OpenClaw Cron**（Job ID: `a061691d-99b9-40ca-bbf0-ac353cbd64f9`），北京时间 6 次/天 |
| **2026-03-22** | 引入「**事件时间**」字段（区分文章发布时间与核心事件实际时间） |
| **2026-03-20** | 黑名单机制废弃，改为 **`includeDomains` 白名单机制**（四级 Tier 体系） |
| **2026-03-18** | v1.3：搜索窗口从固定 24h 改为增量模式；工具名更新为远程 `_exa` 后缀；state.json 新增字段；分级通知策略 |
| **2026-03-17** | `topics-definition.md` 正式定版，成为六大主题分类 Single Source of Truth |
| **2026-03-16** | Skill 初始版本上线：6 搜索维度（A-F）+ 增量采集 + 单日多批次追加 |

---

**版本**: v1.5
**更新时间**: 2026-04-06
**变更**: 新增 Dimension G（Anthropic 专项追踪）；链接字段强制要求；Cron 调度配置；白名单四级 Tier 体系；输出格式规范；与写作系统关系说明

> **维护人**: OpenClaw Agent（Digital11）
> **Skill 路径**: `~/.openclaw/skills/tech-updates-collector/`
> **关联 Skill**: [tech-updates-writer](../tech-updates-writer/SKILL.md)
