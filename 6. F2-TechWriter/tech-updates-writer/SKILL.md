---
name: tech-updates-writer
description: >
  基于每日 AI 日报，通过多 Agent 协作（虾群）流程生产高质量中文科技文章。
  依赖 tech-updates-collector 的日报输出作为素材来源。
  本 Skill 由 Orchestrator Agent 协调执行（见 ORCHESTRATOR.md），
  OpenClaw 主 Agent 只负责启动 Orchestrator 和看门狗监控。
  Activate when: Orchestrator Agent 调度执行,
  或用户要求执行写作系统, 虾群, 写作, 文章, 发布, 协作写作。
---

# Tech Updates Writer — 虾群协作写作系统

基于每日 AI 日报（来自 `tech-updates-collector`），通过多 Agent 协作流程生产高质量中文科技文章并发布到 GitHub Pages。

## 执行架构

本 Skill 的执行由 Orchestrator Agent 协调（详见 `ORCHESTRATOR.md`）：

```
OpenClaw 主 Agent
  └── HEARTBEAT 触发 → sessions_spawn 启动 Orchestrator Agent
                         └── Orchestrator 独立管理 Phase 0-10
                               ├── checkpoint 状态管理（state.json）
                               ├── 失败自动重试（最多 3 次）
                               ├── 内嵌质量门禁（Phase 2/4）
                               └── 完成后通知主 Agent
```

- Orchestrator 的职责和行为规范: `ORCHESTRATOR.md`
- 每个 Phase 的具体执行逻辑: 本文件下方的 Workflow 章节
- 主 Agent 只做两件事: 启动 Orchestrator + 每小时看门狗检查

## Prerequisites

- `tech-updates-collector` Skill 已配置且有日报输出
- 日报文件位置: `../tech-updates-collector/output/` 目录下修改时间最晚的 `.md` 文件
- Node.js 运行环境（用于监控脚本）
- GitHub 发布配置: `publish-config.json`（仓库地址、认证方式、Jekyll 参数）

## 主题分类

参考: #[[file:../tech-updates-collector/topics-definition.md]]

## Workflow

> **执行者**: 以下所有 Phase 由 Orchestrator Agent 按顺序调度。
> 每个 Phase 执行前后，Orchestrator 会写入 checkpoint 到 `state.json`。
> 失败时 Orchestrator 自动重试（最多 3 次），重试仍失败则暂停并告警。
> 详见 `ORCHESTRATOR.md`。

### 实时监控（前置启动）

在开始执行前，Orchestrator 启动实时监控虾：
```bash
node scripts/monitor-launcher.js &
```
功能：每 10 分钟检查进度并主动告知状态，P0 问题立即告警。

### Phase 0: 话题池检查与更新（强制前置）

1. 定位最新日报：检查 `../tech-updates-collector/output/` 目录，选取修改时间最晚的 `.md` 文件作为素材来源
   ```bash
   # 取 output/ 下修改时间最晚的 .md 文件
   LATEST_REPORT=$(ls -t ../tech-updates-collector/output/*.md 2>/dev/null | head -1)
   echo "最新日报: $LATEST_REPORT"
   ```
   - 如目录为空或无 `.md` 文件 → 提示用户先运行 `tech-updates-collector`
   - 如最新文件的修改时间距当前超过 48 小时 → 警告日报可能过期，建议先触发一次 collector 采集
   - 正常情况下直接读取该文件（文件为多轮采集的累积结果，已按 URL 去重）
2. 检查今日话题池是否存在: `selection/YYYY-MM-DD/topic-pool.md`
   - 如不存在 → 从 AI 日报提取话题 （确保至少有20个候选话题）
   - **⚠️ 去重检查（P0 优先级）**：
     * 读取昨天的话题池: `selection/YYYY-MM-DD-1/topic-pool.md`
     * 读取昨天的最终发布: `selection/YYYY-MM-DD-1/YYYY-MM-DD-1-selection.md`（"✅ 最终发布的文章"章节）
     * 排除规则：同一公司/产品的相同事件直接排除；持续报道（连续 3 天以上）排除；关键词重复度 >60% 排除
   - **按六大主题分类提取**：确保每个主题都至少有3个代表性话题
3. 验证话题池质量通过后 → 继续 Phase 1

### Phase 1: 编辑虾选题（选出至少 15个高质量话题）

- 读取话题池: `selection/YYYY-MM-DD/topic-pool.md`
- **⚠️ 强制去重检查（P0 优先级）**：
  - 必须读取昨天的选题文件，检查"✅ 最终发布的文章"章节
  - 排除规则：同一公司/产品的相同角度直接排除；同一事件持续报道排除；关键词重复度 >70% 排除
  - 例外：同一公司/产品的**完全不同角度**可以保留
- **评分标准**：时效性 40%（最重要）+ 热度 25% + 深度 20% + 共鸣度 15%
- **六大主题均衡**：确保所有主题都有覆盖
- **时效性强制要求**：
  - 2026 年素材：40/40 分 ⭐⭐⭐⭐⭐
  - 2025 年素材：20-25/40 分 ⭐⭐⭐
  - 2024 年素材：10/40 分 ⭐（需充分理由）
  - 2023 年及更早：0/40 分，直接淘汰
- 每个话题必须标注素材时间（YYYY-MM）和所属主题
- 输出: `selection/YYYY-MM-DD/YYYY-MM-DD-selection.md`

### Phase 2-4: 流水线模式（创作 → 门禁 → 评审 → 修正）

Phase 2、3、4 采用批次级流水线执行，而非传统的串行模式。

#### 流水线执行模型

```
Batch 1 (3篇): ──创作──→──门禁──→──评审──→──修正──→ done
Batch 2 (3篇):          ──创作──→──门禁──→──评审──→──修正──→ done
Batch 3 (3篇):                   ──创作──→──门禁──→──评审──→ done
Batch 4 (3篇):                            ──创作──→──门禁──→──评审──→──修正──→ done
...

Phase 5 开始 ← 必须等所有 Batch 完成
```

规则：
- 每个 Batch 内部: 3 篇并行（sessions_spawn）
- Batch 间: 流水线推进，Batch N 进入评审时，Batch N+1 开始创作
- 同时最多 2 个 Batch 在执行（避免资源争抢）
- 评审得分 >= 85 的文章跳过修正，直接标记完成
- Phase 5 必须等所有 Batch 的流水线完成后才开始

#### Phase 2: 薛以致用虾创作（每篇 2500-4000 字）

- 要求：中文标点、人类第一人称、数据可验证
- 标注所属主题：每篇文章标注对应的六大主题之一
- 输出: `documents/articles/YYYY-MM-DD/YYYY-MM-DD-poolX-topicY-v1.md`

**⚠️ Phase 2 内嵌质量门禁**（每篇 v1 完成后立即检查）：

| 检查项 | 不通过处理 | 最大重试 |
|--------|-----------|---------|
| 字数 < 2500 或 > 4000 | 在当前 Batch 内重写 | 2 次 |
| 标题/内容与 Phase 1 选题不匹配 | P0，在当前 Batch 内重写，明确要求围绕原始选题创作 | 2 次 |
| 引用 2023 年及更早数据作为主要论据 | 标记警告，记录到 qualityGates | 不重写 |

2 次重写仍不通过 → 标记到 qualityGates，继续流水线（Phase 3 评审时会处理）。

#### Phase 3: 编辑虾评审（4 维度评分）

- 评分维度：内容质量 35% + 可传播性 25% + 价值性 25% + 符合定位 15%
- 输出: `reviews/YYYY-MM-DD-poolX-topicY-v1.md`
- 得分 >= 85 → 跳过 Phase 4 修正，直接标记完成
- 得分 < 85 → 进入 Phase 4 修正

#### Phase 4: 薛以致用虾修正（生成 v2 版本）

- 针对得分 < 85 分或有明确问题的文章
- 单点突破策略：只修正问题点，保持优势部分
- ⚠️ **核心约束（强制）**：
  - ❌ 禁止更换话题主题
  - ❌ 禁止更换核心论点
  - ❌ 禁止更换主要案例
  - ✅ 只能改进表达、补充数据、优化结构
  - ✅ 如果无法在原话题基础上修正到 85 分，标记"无法修正"
- 输出: `documents/articles/YYYY-MM-DD/YYYY-MM-DD-poolX-topicY-v2.md`

**⚠️ Phase 4 内嵌质量门禁**（每篇 v2 完成后立即检查）：

| 检查项 | 判定标准 | 不通过处理 |
|--------|---------|-----------|
| 标题相似度 vs v1 | Jaccard 相似度 < 50% | P0，丢弃 v2，Phase 5 使用 v1 |
| 核心论点一致性 | v2 第一段与 v1 讨论完全不同的主题 | P0，丢弃 v2，使用 v1 |
| 字数范围 | < 2500 或 > 4000 | 标记警告，保留 v2 |

丢弃 v2 保留 v1 不是降级 — v1 本身是合格的创作产出，v2 修正引入了换话题等 P0 问题时，回退到 v1 是正确的质量决策。

### Phase 5: 编辑虾最终选择（共 7 篇）

- 基于综合得分和战略价值，从每个 Pool 选出最佳文章
- ⚠️ **时效性强制检查（核心规则）**：
  - 2026 年素材：40/40 分 ⭐⭐⭐⭐⭐
  - 2025 年素材：20-25/40 分 ⭐⭐⭐
  - 2024 年素材：10/40 分 ⭐（总分上限 70 分）
  - 2023 年及更早：0/40 分，直接淘汰
  - 即使是权威报告（Gartner、McKinsey、HBR），也必须遵守时效性规则
  - 必须在评分中明确标注素材年份
- 输出: `final-selection-YYYY-MM-DD.md`

### Phase 6: 发布虾评估（筛选 >90 分文章）

- 评估维度：传播潜力 30% + 战略价值 25% + 内容成熟度 20% + 实用价值 15% + 风险评估 10%
- 输出: `publication-decision-YYYY-MM-DD.md`

### Phase 7: 发布到 GitHub（自动 commit 和 push）

- 读取 `publish-config.json` 获取仓库配置和认证方式
- 转换为 Jekyll 格式（Front Matter 参数从 `publish-config.json` → `jekyll` 读取）
- 使用序号命名: `YYYY-MM-DD-NN-slug.md`
- 认证方式（由 `publish-config.json` → `auth.method` 决定）：
  - `ssh`: 使用 SSH Key（默认），确保 `auth.sshKeyPath` 指向有效密钥
  - `pat`: 使用 Personal Access Token，从环境变量 `GITHUB_TOKEN` 读取
- Git commit 和 push 到目标仓库
- 输出目录: `publish-config.json` → `github.localCloneDir` + `github.postsDir`

### Phase 8: 生成每日总结报告并主动发送

- 包含：执行摘要、Top 3 文章、质量分布、时间统计、已发布链接、六大主题覆盖情况
- 保存到: `archive/execution-summaries/YYYY-MM-DD-execution-summary.md`
- 主动发送给 human（Feishu 消息 + markdown 文件附件）

### Phase 9: 更新选题文件记录发布结果

- 在当天选题文件顶部添加"✅ 最终发布的文章"章节
- 记录：文章标题、主题关键词、GitHub 文件名、评分
- 目的：供明天 Phase 1 去重检查使用

### Phase 10: 监工虾全流程质量检查（P0 优先级）

- 运行监控脚本: `node scripts/supervisor.js`
- 检查所有 Phase 的执行质量
- 生成监控报告（JSON + Markdown）
- **关键检查项**：Phase 4 是否有换话题（P0）、Phase 5 时效性评分是否正确（P0）
- **主动告警**：发现 P0 问题立即发送警告给 human
- 详细用法参考: `docs/SUPERVISOR-GUIDE.md`

### 更新状态

由 Orchestrator 更新 `state.json`：
- `lastWritingSystemCheck` 更新为当前 Unix 时间戳
- `currentRun.status` 更新为 `"completed"`
- 详见 `ORCHESTRATOR.md` 中的 checkpoint 管理

## 时间约束

- 触发时间: 每日 UTC 07:00（北京 15:00）
- 完成截止: UTC 09:00（北京 17:00）之前
- 预计执行时间: 约 70-80 分钟（流水线模式）

## State

文件: `state.json`

由 Orchestrator 管理，包含 checkpoint 信息。详细结构见 `ORCHESTRATOR.md`。

```json
{
  "lastWritingSystemCheck": 0,
  "currentRun": {
    "date": "",
    "status": "idle",
    "orchestratorStartTime": null,
    "endTime": null,
    "currentPhase": null,
    "totalRetries": 0,
    "monitorPid": null,
    "checkpoints": {},
    "qualityGates": {}
  }
}
```

状态流转: `idle → running → completed / paused / failed`

## 目录结构

```
tech-updates-writer/
├── SKILL.md                          # 本文件（Phase 具体逻辑）
├── ORCHESTRATOR.md                   # Orchestrator Agent 定义（协调、checkpoint、重试）
├── state.json                        # 运行状态（含 checkpoint）
├── publish-config.json               # GitHub 发布配置（仓库、认证、Jekyll 参数）
├── scripts/
│   ├── supervisor.js                 # 监工虾
│   ├── realtime-supervisor.js        # 实时监控虾
│   ├── monitor-launcher.js           # 监控启动器
│   └── notification-helper.js        # 通知助手
├── docs/
│   ├── SUPERVISOR-GUIDE.md           # 监工虾使用指南
│   └── REALTIME-MONITOR-GUIDE.md     # 实时监控使用指南
├── selection/                        # 每日选题
│   └── YYYY-MM-DD/
├── documents/articles/               # 文章草稿
│   └── YYYY-MM-DD/
├── reviews/                          # 评审记录
├── archive/                          # 归档
│   └── execution-summaries/
├── final-selection-YYYY-MM-DD.md     # 最终选择
└── publication-decision-YYYY-MM-DD.md # 发布决策
```

## Troubleshooting

| 问题 | 处理 |
|------|------|
| 日报不存在 | 确认 `../tech-updates-collector/output/` 目录下有 `.md` 文件；如为空，先运行 `tech-updates-collector` |
| 日报过期（>48h） | 最新日报修改时间过旧，先触发一次 collector 采集 |
| 监工虾路径错误 | 检查 `WRITER_BASE_DIR` 环境变量 |
| Phase 4 换话题 | P0 问题，Phase 4 内嵌门禁会自动丢弃 v2 并保留 v1 |
| Phase 5 时效性评分错误 | P0 问题，检查评分逻辑 |
| GitHub push 失败 | 检查 `publish-config.json` 中的认证配置；SSH 方式检查密钥，PAT 方式检查 `GITHUB_TOKEN` 环境变量 |
| Phase 执行超时 | Orchestrator 自动重试最多 3 次；3 次仍失败则暂停并告警，等待人工介入 |
| state.json 损坏 | 从 state.json.bak 恢复（Orchestrator 每次写入前自动备份） |
| Orchestrator 僵死 | 主 Agent 看门狗检测到 > 3 小时无进展，标记 failed 并重启 |
