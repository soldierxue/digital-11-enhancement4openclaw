---
name: tech-updates-collector
description: >
  按六大主题从 Twitter/X、博客、论文等来源采集 AI 资讯，生成结构化日报。
  通过 kiro-cli 调用 Exa MCP 工具执行搜索。
  Activate when: heartbeat 定时触发, 或用户要求执行 AI 日报采集,
  tech updates, 日报, 采集, AI资讯, 技术更新, 每日更新。
---

# Tech Updates Collector

按六大主题从 Twitter/X、博客、论文等来源采集 AI 资讯，生成结构化日报 `output/YYYY-MM-DD.md`。

## Prerequisites

- Kiro CLI 已安装并登录（`kiro-cli auth status`）
- Exa MCP Server 已配置（`~/.kiro/settings/mcp.json` 中有 `exa` 条目）
- 验证: `kiro-cli chat --no-interactive --trust-all-tools "use Exa web_search for: test query"`

## 主题分类与搜索策略

参考 `topics-definition.md`（Single Source of Truth），包含：

**六大主题**（输出分类维度）:
1. 🤖 **openclaw** — AI Agent 能力与平台
2. 🏢 **ai-org-structure** — AI 时代的组织变革
3. 💼 **agentic-cases** — AI Agent 实战案例
4. 🛒 **agentic-commerce** — AI 商业应用
5. 🏭 **enterprise-ai** — 企业 AI 应用
6. ⚙️ **ai-dlc** — AI 开发生命周期

**搜索策略维度** (Dimension A-F): 定义了 6 组搜索关键词和来源策略  
**重点关注来源**: 行业领袖 Twitter 账号、特定博客（Gary Marcus 等）  
**重点跟踪公司**: AI 基础模型公司、企业 AI 平台、云服务商、半导体等

> 搜索策略维度是采集阶段的组织方式，六大主题是输出阶段的分类方式。两者正交。

## Workflow

### Step 0: 检查是否需要执行

```bash
# 读取 state.json 中的 lastCollectorCheck 时间戳
# 如果距上次执行不足 1 小时，跳过
```

### Step 1: 执行搜索（通过 kiro-cli → Exa MCP）

按 `topics-definition.md` 中定义的 6 个搜索策略维度（Dimension A-F）执行。

**⏰ 时间窗口（强制）**: 所有搜索必须限制为当前系统时间倒推 24 小时内的内容。
- 计算方式: 取当前 UTC 时间，减去 24 小时，格式化为 ISO 8601（`YYYY-MM-DDTHH:MM:SS.000Z`）
- 传参: Exa twitter_search 使用 `startPublishedDate`，Exa web_search 使用 `startPublishedDate`
- 示例: 若当前为 `2026-03-17T10:00:00Z`，则 `startPublishedDate='2026-03-16T10:00:00.000Z'`

**Search A — General AI/Tech News (Twitter/X)**:
```bash
kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa twitter_search: query='AI OR GenAI OR Anthropic OR Claude OR OpenAI OR DeepSeek OR semiconductors OR AI chips OR layoffs OR workforce', numResults=20, startPublishedDate='<24h-ago-ISO>'"
```

**Search B — Industry Leaders (Twitter/X)**:
```bash
kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa twitter_search: query='from:sama OR from:elonmusk OR from:satyanadella OR from:sundarpichai OR from:karpathy OR from:ylecun AI OR tech OR announcement', numResults=15, startPublishedDate='<24h-ago-ISO>'"
```

**Search C — Enterprise AI (Twitter/X + Web)**:
```bash
kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa twitter_search: query='Palantir OR Salesforce OR ServiceNow OR Workday OR Agentforce', numResults=15, startPublishedDate='<24h-ago-ISO>'"
```

**Search D — Gary Marcus 博客**:
```bash
kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa web_search: query='Gary Marcus AI', numResults=5, startPublishedDate='<24h-ago-ISO>'"
```

**Search E — AI Native 创业公司 (Twitter/X)**:
```bash
kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa twitter_search: query='AI startup OR AI native OR YC AI OR seed round OR series A OR funding', numResults=15, startPublishedDate='<24h-ago-ISO>'"
```

**Search F — AWS Cloud (Twitter/X + Web)**:
```bash
kiro-cli chat --no-interactive --trust-all-tools \
  "use Exa twitter_search: query='AWS OR Amazon Web Services OR Bedrock OR SageMaker OR AWS AI', numResults=15, startPublishedDate='<24h-ago-ISO>'"
```

> `<24h-ago-ISO>` 为占位符，执行时由 Agent 根据当前系统时间动态计算替换。

### Step 2: 按六大主题分类

将搜索结果按 `topics-definition.md` 中的匹配规则分类：
1. 精确匹配: 直接包含关键词 → 归入对应主题
2. 语义匹配: 根据内容判断最相关主题
3. 多主题: 一条新闻可归入多个主题（交叉标注）
4. 未分类: 不符合六大主题 → "其他/Misc"

### Step 3: 生成日报（增量追加去重模式）

输出文件: `output/YYYY-MM-DD.md`（每日一个文件，多次执行增量追加）

> ⚠️ **核心机制**：collector 每天通过 HEARTBEAT 执行多次（每 1+ 小时），同一天的日报文件不会被覆盖，而是增量追加新发现的条目。

**执行逻辑**：

```
1. 检查 output/YYYY-MM-DD.md 是否已存在
   ├── 不存在 → 创建新文件，写入全部搜索结果（首次采集）
   └── 已存在 → 进入增量追加流程：
       a. 读取现有文件，提取所有已收录条目的链接（URL）作为去重索引
       b. 将本次搜索结果逐条与已收录链接比对
       c. 仅将新条目（链接不在已收录集合中的）追加到对应主题章节末尾
       d. 新条目的序号接续该主题已有条目的最大序号
       e. 重新计算并更新文件末尾的「📊 本期统计」和「🔍 本期趋势」
       f. 更新文件头部的「更新时间」为当前时间
```

**去重规则**：
- 主键：条目的 `链接` 字段（URL 精确匹配）
- 同一 URL 不同主题交叉标注的情况：以首次归入的主题为准，不重复追加
- 如果本次搜索无新条目，仅更新「更新时间」，不修改其他内容

**追加格式**：新条目追加到对应主题章节的最后一条之后，保持与现有条目相同的 markdown 格式：

```markdown
### N+1. [新标题]
- 来源: ...
- 时间: ...
- 摘要: ...
- 关键词: #tag1 #tag2
- 链接: https://...
```

**完整文件格式**（首次创建时）：

```markdown
# Tech Updates - YYYY-MM-DD

**更新时间**: YYYY-MM-DD HH:MM UTC（每次采集后更新）
**采集次数**: N（当日累计执行次数）
**来源**: Twitter/X, 博客, 技术媒体 (via Exa MCP)

---

## 📚 主题索引
- [🤖 openclaw](#openclaw) - N条
- [🏢 ai-org-structure](#ai-org-structure) - N条
- [💼 agentic-cases](#agentic-cases) - N条
- [🛒 agentic-commerce](#agentic-commerce) - N条
- [🏭 enterprise-ai](#enterprise-ai) - N条
- [⚙️ ai-dlc](#ai-dlc) - N条

---

## 🤖 openclaw
### 1. [标题]
- 来源: ...
- 时间: ...
- 摘要: ...
- 关键词: #agent #autonomous
- 链接: ...

(以此类推各主题)

## 📊 本期统计
- 总更新数: N条
- 主题分布: openclaw X%, ai-org-structure Y%, ...
- 本次新增: M条（仅增量追加时显示）

## 🔍 本期趋势
1. ...
2. ...
```

> 📌 **对 F2 writer 的影响**：无。Writer 在 Phase 0 读取 `../tech-updates-collector/output/YYYY-MM-DD.md` 时，看到的是当日所有采集轮次的累积结果，无需关心文件是一次生成还是多次追加。

### Step 4: 更新状态

更新 `state.json` 中的 `lastCollectorCheck` 为当前 Unix 时间戳。

### Step 5: 通知

主动发送日报给 human（Feishu 消息 + markdown 文件附件）。

## State

文件: `state.json`

```json
{
  "lastCollectorCheck": 0
}
```

## Output

日报文件存放在 `output/` 目录，每日一个文件，多次执行增量追加：
```
output/
├── 2026-03-16.md    # 3月16日累积日报（可能经过多次追加）
├── 2026-03-17.md    # 3月17日累积日报
└── ...
```

> 同一天的文件不会被覆盖。每次执行时，新发现的条目（URL 去重后）追加到对应主题章节末尾，统计和趋势部分重新生成。F2 writer 读取时看到的是当日完整累积结果。

## Troubleshooting

| 问题 | 处理 |
|------|------|
| kiro-cli 未安装 | `kiro-cli auth status` 检查，参考 `3. KiroCLI/kiro_install_config.md` |
| Exa 搜索无结果 | 检查 `~/.kiro/settings/mcp.json` 中 exa 配置 |
| 搜索超时 | 拆分为更小的查询批次；检查网络连接 |
| 日报格式异常 | 参考 `output/` 中的历史日报样例 |
