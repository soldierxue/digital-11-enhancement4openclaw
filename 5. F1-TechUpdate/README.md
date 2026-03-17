# Tech Updates Collector — OpenClaw 安装配置指南

## 1. Skill 简介

`tech-updates-collector` 是一个 AI 资讯采集 Skill，按六大主题（openclaw、ai-org-structure、agentic-cases、agentic-commerce、enterprise-ai、ai-dlc）从 Twitter/X、博客、论文等来源自动采集资讯，生成结构化日报 `output/YYYY-MM-DD.md`。

搜索能力通过宿主机上的 Kiro CLI 调用 Exa MCP Server 实现。

---

## 2. 目录结构

```
skills/tech-updates-collector/
├── SKILL.md                 # Skill 定义（触发条件、搜索策略、输出格式）
├── topics-definition.md     # 六大主题权威定义（Single Source of Truth）
├── state.json               # 采集状态 {"lastCollectorCheck": <unix_timestamp>}
└── output/                  # 日报输出目录
    └── 2026-03-16.md        # 历史日报样例
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

检查配置文件 `~/.kiro/settings/mcp.json`，确认存在 `exa` 相关条目：

```json
{
  "mcpServers": {
    "github.com/exa-labs/exa-mcp-server": {
      "command": "npx",
      "args": ["exa-mcp-server", "--tools=web_search,research_paper_search,twitter_search,company_research,crawling,competitor_finder"],
      "env": {
        "EXA_API_KEY": "<your-api-key>"
      },
      "disabled": false
    }
  }
}
```

验证 Exa MCP 可用：

```bash
kiro-cli chat --no-interactive --trust-all-tools "use Exa web_search for: test query"
```

### 3.3 Node.js（可选）

日报生成由 OpenClaw Agent 直接完成，不依赖 Node.js。但如果需要运行 writer Skill 的监控脚本，需要 Node.js 18+。

---

## 4. 安装步骤

### Step 1: 复制 Skill 到 OpenClaw skills 目录

```bash
# 假设 OpenClaw 工作目录为 ~/openclaw
cp -r skills/tech-updates-collector ~/openclaw/skills/tech-updates-collector
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

在 OpenClaw 的 `HEARTBEAT.md` 中添加以下段落：

```markdown
## Tech Updates 采集 📰 (every 1+ hour)
If 1+ hour since last check (see `skills/tech-updates-collector/state.json` → `lastCollectorCheck`):
- 参考 `skills/tech-updates-collector/SKILL.md` 执行采集流程
- 通过 kiro-cli 调用 Exa MCP 工具搜索 AI 资讯
- 按六大主题分类生成日报: `skills/tech-updates-collector/output/YYYY-MM-DD.md`
- 更新 `skills/tech-updates-collector/state.json` 中的 `lastCollectorCheck` 时间戳
- 主动发送日报给 human（Feishu 消息 + markdown 文件附件）
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
  → 按 6 组搜索策略调用 kiro-cli → Exa MCP
  → 搜索结果按 topics-definition.md 分类
  → 生成 output/YYYY-MM-DD.md
  → 更新 state.json
  → 发送日报给 human
```

---

## 7. 常见问题

| 问题 | 排查方法 |
|------|----------|
| kiro-cli 未安装 | `kiro-cli --version`，参考安装文档 |
| Exa 搜索无结果 | 检查 `~/.kiro/settings/mcp.json` 中 Exa 配置和 API Key |
| 搜索超时 | 拆分为更小的查询批次；检查网络连接 |
| 日报格式异常 | 参考 `output/2026-03-16.md` 样例对比 |
| state.json 时间戳不更新 | 检查 Agent 是否有文件写入权限 |

---

**版本**: v1.0  
**更新时间**: 2026-03-17
