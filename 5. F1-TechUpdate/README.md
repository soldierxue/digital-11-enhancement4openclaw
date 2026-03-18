# Tech Updates Collector — OpenClaw 安装配置指南

> 本文档供 OpenClaw Agent 读取并在宿主机上执行，完成 tech-updates-collector Skill 的安装与配置。
>
> 幂等性原则：所有操作执行前先检查当前状态，已存在的配置只验证不重复写入，重复执行不会产生副作用。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档所有章节（第 1 ~ 7 节），理解：
- 目标：安装 `tech-updates-collector` Skill，配置 HEARTBEAT.md 定时采集任务
- 核心依赖：Kiro CLI（已安装且登录）+ Exa MCP Server（已配置在 `~/.kiro/settings/mcp.json`）
- Skill 文件位置：`~/openclaw/skills/tech-updates-collector/`（或实际 OpenClaw 工作目录下）
- 最终验收标准：Skill 文件就位、依赖可用、HEARTBEAT.md 已包含采集任务段落

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

# 8. HEARTBEAT.md 中是否已有采集任务
grep -c "Tech Updates 采集" "$OC_DIR/HEARTBEAT.md" 2>/dev/null || echo "HEARTBEAT_TASK_NOT_FOUND"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应文档 | 前置条件 | 需要用户确认的情况 |
|------|----------|----------|-------------------|
| 阶段 1：依赖检查 | 第 3 节 | 无 | Kiro CLI 未安装/未登录时暂停；Exa MCP 未配置时暂停，引导参考 `3. KiroCLI/kiro_mcp_recommended.md` |
| 阶段 2：安装 Skill 文件 | 第 4 节 Step 1-4 | 阶段 1 通过 | Skill 目录已存在时跳过复制，仅验证文件完整性 |
| 阶段 3：配置 HEARTBEAT.md | 第 5 节 | 阶段 2 完成 | `Tech Updates 采集` 段落已存在时跳过，仅验证内容 |
| 阶段 4：端到端验证 | 第 6-7 节 | 阶段 3 完成 | 验证失败时展示错误并等待用户决策 |

### 执行原则

1. **先诊断，后执行** — 不要跳过状态检查直接复制文件或修改配置
2. **幂等性优先** — Skill 目录已存在时不覆盖，HEARTBEAT.md 段落已存在时不重复追加
3. **遇到异常立即暂停** — 依赖缺失、文件权限不足等情况，停下来向用户说明
4. **每阶段汇报** — 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续
5. **已完成的步骤可跳过** — 如果诊断发现 Skill 已安装且文件完整，直接标记 ✅ 跳过

---

## 1. Skill 简介

`tech-updates-collector` 是一个 AI 资讯采集 Skill，按六大主题（openclaw、ai-org-structure、agentic-cases、agentic-commerce、enterprise-ai、ai-dlc）从博客、新闻等来源自动采集资讯，生成结构化日报 `output/YYYY-MM-DD.md`。每日多次执行时采用增量追加去重模式：按 URL 去重，仅追加新条目到对应主题章节末尾，不覆盖已有内容。

搜索能力通过宿主机上的 Kiro CLI 调用 Exa MCP Server 实现（远程 URL 模式，工具名带 `_exa` 后缀）。推荐使用 `web_search_advanced_exa` 的日期过滤功能，配合增量搜索窗口（`lastCheck → now`）精确限制采集范围，避免重复搜索。

---

## 2. 目录结构

```
skills/tech-updates-collector/
├── SKILL.md                 # Skill 定义（触发条件、搜索策略、输出格式）
├── topics-definition.md     # 六大主题权威定义（Single Source of Truth）
├── state.json               # 采集状态 {"lastCollectorCheck", "todayFile", "todayBatchCount", "todayTotalItems"}
└── output/                  # 日报输出目录（每日一个文件，增量追加去重）
    └── 2026-03-16.md        # 历史日报样例（多次采集的累积结果）
```

---

## 3. 依赖条件

### 3.1 Kiro CLI

Kiro CLI 必须安装在 OpenClaw 同一台宿主机上，并已登录。

```bash
# 检查安装
kiro-cli --version

# 检查登录状态
kiro-cli auth status
```

如未安装，参考 `3. KiroCLI/kiro_install_config.md`。

### 3.2 Exa MCP Server

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
| `web_search_advanced_exa` | 高级搜索，支持 `startPublishedDate` / `endPublishedDate` 日期过滤 | ✅ 精确限制 24h 采集窗口 |
| `company_research_exa` | 公司研究 | 企业 AI 动态 |
| `crawling_exa` | 网页内容抓取 | 深度阅读原文 |
| `people_search_exa` | 人物搜索 | AI 领域关键人物 |

> `web_search_advanced_exa` 的日期过滤能力对日报采集至关重要 — 可以精确限制搜索窗口为过去 24 小时，避免重复采集旧资讯。

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

### 3.3 Node.js（可选）

日报生成由 OpenClaw Agent 直接完成，不依赖 Node.js。但如果需要运行 writer Skill 的监控脚本，需要 Node.js 18+。

---

## 4. 安装步骤

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

## 5. HEARTBEAT.md 定时任务配置

在 HEARTBEAT.md 中添加以下段落（幂等）。先检查是否已存在：

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

**触发机制说明**：
- OpenClaw 的 `startHeartbeatRunner` 按配置间隔读取 HEARTBEAT.md
- Agent 读取后检查 `state.json` 中的 `lastCollectorCheck` 时间戳
- 如果距上次执行超过 1 小时，执行 SKILL.md 中定义的采集流程
- 执行完成后更新时间戳，避免重复执行

---

## 6. 工作流概览

```
HEARTBEAT.md 触发
  → Agent 读取 SKILL.md
  → 检查 state.json（是否需要执行）
  → 计算搜索窗口（增量: lastCheck → now，兜底: now-24h → now）
  → 按 6 组搜索策略调用 kiro-cli → Exa MCP
    （使用 web_search_advanced_exa / twitter_search_exa 限制时间窗口）
  → 搜索结果按 topics-definition.md 分类
  → 增量追加去重写入 output/YYYY-MM-DD.md
    （首次创建新文件；后续执行按 URL 去重，仅追加新条目）
  → 更新统计和趋势章节
  → 更新 state.json（时间戳 + todayFile + batchCount + totalItems）
  → 分级通知（首次→完整日报，≥5条→摘要，<5条→静默，0条→不通知）
```

---

## 7. 常见问题

| 问题 | 排查方法 |
|------|----------|
| kiro-cli 未安装 | `kiro-cli --version`，参考安装文档 |
| Exa 搜索无结果 | 检查 `~/.kiro/settings/mcp.json` 中 Exa 配置；确认使用远程 URL 模式而非本地 npx |
| Exa 只有 2 个工具 | 本地 npx 模式（v3.1.9+）已不支持 `--tools` 参数，切换到远程 URL 模式 |
| 工具名报错 (twitter_search 不存在) | 远程 URL 模式工具名带 `_exa` 后缀：`twitter_search_exa`、`web_search_advanced_exa` |
| 缺少日期过滤能力 | 确认远程 URL 中包含 `web_search_advanced_exa` 工具 |
| 搜索超时 | 拆分为更小的查询批次；检查网络连接 |
| 日报格式异常 | 参考 `output/2026-03-16.md` 样例对比 |
| 日报条目重复 | 检查去重逻辑是否按 URL 精确匹配；确认未手动修改条目链接 |
| 多次执行后条目序号不连续 | 正常现象 — 新条目序号接续该主题已有最大序号，不会重新编号 |
| state.json 时间戳不更新 | 检查 Agent 是否有文件写入权限 |
| 每次都搜 24h 没有增量效果 | 检查 `state.json` 的 `lastCollectorCheck` 是否正常更新；值为 0 或过期 >24h 会触发兜底全量搜索 |
| 出现 YYYY-MM-DD-evening.md 等异常文件名 | 日报文件名必须严格为 `YYYY-MM-DD.md`，不允许后缀变体；删除异常文件 |
| 通知过于频繁 | 分级通知：增量 <5 条应静默追加，0 条不通知；检查 SKILL.md Step 5 通知策略 |

---

**版本**: v1.3  
**更新时间**: 2026-03-18  
**变更**: 搜索窗口从固定 24h 改为增量模式（lastCheck → now，兜底 cap 24h）；工具名更新为远程 `_exa` 后缀；state.json 新增 todayFile/todayBatchCount/todayTotalItems 字段；新增分级通知策略
