# Tech Updates Writer — OpenClaw 安装配置指南

> 本文档供 OpenClaw Agent 读取并在宿主机上执行，完成 tech-updates-writer Skill 的安装与配置。
>
> 幂等性原则：所有操作执行前先检查当前状态，已存在的配置只验证不重复写入，重复执行不会产生副作用。
>
> **v2 架构变更**：写作系统现在由独立的 Orchestrator Agent 协调执行，OpenClaw 主 Agent 只负责启动和看门狗监控。详见 `ORCHESTRATOR.md`。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档所有章节（第 1 ~ 8 节），理解：
- 目标：安装 `tech-updates-writer` Skill，配置 HEARTBEAT.md 定时写作任务
- 核心前置依赖：`tech-updates-collector` Skill 已安装且有日报输出（F1 → F2 数据流水线）
- 其他依赖：Node.js 18+（监控脚本）、Git + SSH/PAT（Phase 7 GitHub 发布）
- Skill 文件位置：`~/openclaw/skills/tech-updates-writer/`（或实际 OpenClaw 工作目录下）
- 最终验收标准：Skill 文件就位、collector 依赖可用、publish-config.json 已配置、HEARTBEAT.md 已包含写作任务段落

### 第二步：检查当前环境状态

通读完成后，先执行以下诊断命令，收集当前状态：

```bash
# 1. OpenClaw 工作目录（取实际路径，以下用 $OC_DIR 代替）
OC_DIR="$HOME/.openclaw"
echo "OpenClaw 工作目录: $OC_DIR"

# 2. Writer Skill 是否已安装
ls "$OC_DIR/skills/tech-updates-writer/SKILL.md" 2>/dev/null \
  && echo "WRITER_SKILL_INSTALLED" || echo "WRITER_SKILL_NOT_INSTALLED"

# 3. Collector Skill 是否已安装（前置依赖）
ls "$OC_DIR/skills/tech-updates-collector/SKILL.md" 2>/dev/null \
  && echo "COLLECTOR_INSTALLED" || echo "COLLECTOR_NOT_INSTALLED"

# 4. Collector 最新日报（取修改时间最晚的文件）
LATEST=$(ls -t "$OC_DIR/skills/tech-updates-collector/output/"*.md 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
  MOD_TIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$LATEST" 2>/dev/null || stat -c "%y" "$LATEST" 2>/dev/null | cut -d. -f1)
  echo "COLLECTOR_LATEST_REPORT=$LATEST mod=$MOD_TIME"
else
  echo "COLLECTOR_NO_OUTPUT"
fi

# 5. topics-definition.md 是否存在（writer 通过文件引用读取）
ls "$OC_DIR/skills/tech-updates-collector/topics-definition.md" 2>/dev/null \
  && echo "TOPICS_DEF_EXISTS" || echo "TOPICS_DEF_MISSING"

# 6. Node.js 版本（监控脚本依赖）
node --version 2>/dev/null || echo "NODE_NOT_FOUND"

# 7. Git 是否可用（Phase 7 发布依赖）
git --version 2>/dev/null || echo "GIT_NOT_FOUND"

# 8. SSH 认证是否可用（GitHub 发布依赖）
ssh -T git@github.com 2>&1 | head -1 || echo "SSH_AUTH_UNKNOWN"

# 9. publish-config.json 是否已配置
python3 -c "
import json, os
p = os.path.expanduser('$OC_DIR/skills/tech-updates-writer/publish-config.json')
d = json.load(open(p))
print(f'PUBLISH_CONFIG_OK repo={d.get(\"github\",{}).get(\"repo\",\"MISSING\")} auth={d.get(\"auth\",{}).get(\"method\",\"MISSING\")}')
" 2>/dev/null || echo "PUBLISH_CONFIG_INVALID_OR_MISSING"

# 10. HEARTBEAT.md 中是否已有写作任务
grep -c "虾群协作写作系统" "$OC_DIR/HEARTBEAT.md" 2>/dev/null || echo "HEARTBEAT_WRITER_NOT_FOUND"

# 11. state.json 是否存在且合法
python3 -c "
import json, os
p = os.path.expanduser('$OC_DIR/skills/tech-updates-writer/state.json')
d = json.load(open(p))
print(f'STATE_OK lastWritingSystemCheck={d.get(\"lastWritingSystemCheck\", \"MISSING\")}')
" 2>/dev/null || echo "STATE_JSON_INVALID_OR_MISSING"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应文档 | 前置条件 | 需要用户确认的情况 |
|------|----------|----------|-------------------|
| 阶段 1：前置依赖检查 | 第 3 节 | 无 | Collector 未安装时暂停，引导参考 `5. F1-TechUpdate/README.md`；Node.js 版本 < 18 时暂停 |
| 阶段 2：安装 Skill 文件 | 第 4 节 Step 1-3 | 阶段 1 通过 | Skill 目录已存在时跳过复制，仅验证文件完整性（含 ORCHESTRATOR.md） |
| 阶段 3：配置 GitHub 发布 | 第 4 节 Step 4 | 阶段 2 完成 | `publish-config.json` 中的 `remoteUrl` 和 `auth` 需用户确认；SSH 认证失败时暂停 |
| 阶段 4：配置 HEARTBEAT.md | 第 5 节 | 阶段 3 完成 | `虾群协作写作系统` 段落已存在时跳过；确认包含 Orchestrator 委托模式和看门狗段落 |
| 阶段 5：端到端验证 | 第 7-8 节 | 阶段 4 完成 | 监控脚本执行失败时展示错误并等待用户决策 |

### 执行原则

1. **先诊断，后执行** — 不要跳过状态检查直接复制文件或修改配置
2. **幂等性优先** — Skill 目录已存在时不覆盖，HEARTBEAT.md 段落已存在时不重复追加
3. **Collector 是硬依赖** — 如果 `tech-updates-collector` 未安装或无日报输出，必须先完成 F1 安装
4. **GitHub 发布配置需用户确认** — `publish-config.json` 中的仓库地址和认证方式涉及用户个人信息，不要自行填写
5. **遇到异常立即暂停** — 依赖缺失、文件权限不足等情况，停下来向用户说明
6. **每阶段汇报** — 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续
7. **已完成的步骤可跳过** — 如果诊断发现 Skill 已安装且文件完整，直接标记 ✅ 跳过

---

## 1. Skill 简介

`tech-updates-writer` 是一个多 Agent 协作写作 Skill（虾群协作写作系统），基于 `tech-updates-collector` 产出的每日 AI 日报，通过 Phase 0-10 的完整流水线生产高质量中文科技文章并发布到 GitHub Pages。

核心流程：话题池生成 → 编辑虾选题 → 薛以致用虾创作 → 编辑虾评审 → 修正 → 最终选择 → 发布评估 → GitHub 发布 → 监工虾质量检查。

---

## 2. 目录结构

```
skills/tech-updates-writer/
├── SKILL.md                          # Skill 定义（Phase 0-10 工作流 + 内嵌质量门禁）
├── ORCHESTRATOR.md                   # Orchestrator Agent 定义（协调、checkpoint、重试）
├── state.json                        # 运行状态（含 checkpoint + qualityGates）
├── publish-config.json               # GitHub 发布配置（仓库、认证、Jekyll 参数）
├── scripts/                          # 监控与质量检查脚本
│   ├── supervisor.js                 # 监工虾 — 事后全面质量检查
│   ├── realtime-supervisor.js        # 实时监控虾 — 执行期间每 10 分钟检查
│   ├── monitor-launcher.js           # 监控启动器 — 启动实时监控 + 告警检查
│   └── notification-helper.js        # 通知助手 — 读取通知文件并发送
├── docs/                             # 使用指南
│   ├── SUPERVISOR-GUIDE.md           # 监工虾详细使用指南
│   └── REALTIME-MONITOR-GUIDE.md     # 实时监控详细使用指南
├── selection/                        # [运行时生成] 每日选题
│   └── YYYY-MM-DD/
├── documents/articles/               # [运行时生成] 文章草稿
│   └── YYYY-MM-DD/
├── reviews/                          # [运行时生成] 评审记录
├── archive/                          # [运行时生成] 归档
│   └── execution-summaries/
├── final-selection-YYYY-MM-DD.md     # [运行时生成] 最终选择
└── publication-decision-YYYY-MM-DD.md # [运行时生成] 发布决策
```

---

## 3. 依赖条件

### 3.1 tech-updates-collector Skill（必需，前置依赖）

Writer 是 F2 阶段的 Skill，它的素材来源完全依赖 F1 阶段的 `tech-updates-collector` Skill 产出的每日 AI 日报。两者构成一条数据流水线：

```
F1: tech-updates-collector（采集）→ output/YYYY-MM-DD.md（增量追加去重） → F2: tech-updates-writer（写作）
```

**依赖关系详情**：

| 依赖项 | 路径 | 说明 |
|--------|------|------|
| 每日 AI 日报 | `../tech-updates-collector/output/` 目录下修改时间最晚的 `.md` 文件 | Phase 0 强制检查，目录为空则中止写作流程。取最新文件而非硬编码当天日期，兼容跨日执行场景 |
| 主题定义 | `../tech-updates-collector/topics-definition.md` | 通过 `#[[file:...]]` 引用，六大主题分类的唯一权威来源 |

**确认 collector 已安装并有输出**：

```bash
# 1. 确认 collector Skill 存在
ls skills/tech-updates-collector/SKILL.md

# 2. 确认有日报输出（至少有一天的数据）
ls skills/tech-updates-collector/output/

# 3. 确认主题定义文件存在
ls skills/tech-updates-collector/topics-definition.md
```

**执行顺序**：collector 每小时执行一次（通过 HEARTBEAT.md 触发），采用增量追加去重模式写入日报。writer 每日 UTC 07:00 触发，Phase 0 自动选取 `output/` 目录中修改时间最晚的日报文件作为素材，无需硬编码当天日期。正常情况下 writer 启动时最新日报已包含多轮采集的累积结果。如果 `output/` 目录为空，Phase 0 会提示用户先运行 collector。

两个 Skill 通过文件松耦合，不共享状态（各自维护独立的 `state.json`）。

> 📌 如果尚未安装 collector，请先参考 `5. F1-TechUpdate/README.md` 完成安装配置。

### 3.2 Node.js 18+（必需）

监控脚本（supervisor.js 等）需要 Node.js 运行环境：

```bash
node --version  # 需要 v18+
```

### 3.3 环境变量（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WRITER_BASE_DIR` | Skill 根目录（`scripts/` 的上一级） | 写作系统工作目录 |
| `GITHUB_TOKEN` | （无） | GitHub Personal Access Token，仅当 `publish-config.json` 中 `auth.method` 为 `pat` 时需要 |

脚本会自动使用相对路径作为默认值，通常无需手动设置。如果 OpenClaw 的工作目录结构不同，可通过环境变量覆盖。

### 3.4 publish-config.json（Phase 7 发布必需）

GitHub Pages 发布的所有配置集中在 `publish-config.json` 中：

```json
{
  "github": {
    "repo": "jason.xue",
    "branch": "main",
    "postsDir": "_posts",
    "localCloneDir": "/tmp/jason.xue",
    "remoteUrl": "git@github.com:<username>/jason.xue.git"
  },
  "auth": {
    "method": "ssh",
    "sshKeyPath": "~/.ssh/id_ed25519"
  },
  "jekyll": {
    "layout": "post",
    "defaultCategories": ["AI", "Tech"],
    "filenamePattern": "YYYY-MM-DD-NN-slug.md"
  }
}
```

**配置项说明**：

| 字段 | 说明 |
|------|------|
| `github.repo` | GitHub 仓库名 |
| `github.branch` | 推送的目标分支 |
| `github.postsDir` | Jekyll 文章目录（相对于仓库根目录） |
| `github.localCloneDir` | 本地 clone 路径 |
| `github.remoteUrl` | 仓库远程地址（SSH 或 HTTPS 格式） |
| `auth.method` | 认证方式：`ssh`（默认）或 `pat` |
| `auth.sshKeyPath` | SSH 私钥路径（`method=ssh` 时使用） |
| `jekyll.layout` | Jekyll Front Matter 的 layout 值 |
| `jekyll.defaultCategories` | 默认文章分类 |
| `jekyll.filenamePattern` | 文件命名规则 |

**认证方式选择**：

- SSH（推荐）：确保 `auth.sshKeyPath` 指向有效的 SSH 私钥，且公钥已添加到 GitHub
  ```bash
  ssh -T git@github.com  # 验证 SSH 连接
  ```
- Personal Access Token：将 `auth.method` 改为 `pat`，设置环境变量 `GITHUB_TOKEN`，并将 `github.remoteUrl` 改为 HTTPS 格式
  ```bash
  export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
  # remoteUrl 改为: https://github.com/<username>/jason.xue.git
  ```

### 3.5 Git（Phase 7 发布需要）

Phase 7 需要 git 来 commit 和 push 文章到 GitHub Pages 仓库：

```bash
git --version

# 确认本地 clone 目录存在且是 git 仓库（路径见 publish-config.json → github.localCloneDir）
ls /tmp/jason.xue/_posts
```

### 3.6 主题定义引用

Writer 通过文件引用读取 collector 的主题定义：

```
#[[file:../tech-updates-collector/topics-definition.md]]
```

不需要在 writer 中维护主题定义副本。

---

## 4. 安装步骤

### Step 1: 复制 Skill 到 OpenClaw skills 目录

先检查 Skill 是否已安装：

```bash
OC_SKILL_DIR="$HOME/.openclaw/skills/tech-updates-writer"
if [ -f "$OC_SKILL_DIR/SKILL.md" ]; then
  echo "✔ tech-updates-writer Skill 已安装，跳过复制"
else
  echo "安装 tech-updates-writer Skill..."
  cp -r skills/tech-updates-writer "$OC_SKILL_DIR"
  echo "✔ Skill 已复制到 $OC_SKILL_DIR"
fi
```

### Step 2: 确认 F1 collector Skill 已安装且可用

```bash
# 确认 collector Skill 存在
ls ~/openclaw/skills/tech-updates-collector/SKILL.md

# 确认主题定义存在（writer 通过文件引用读取）
ls ~/openclaw/skills/tech-updates-collector/topics-definition.md

# 确认有日报输出（writer Phase 0 依赖此文件）
ls ~/openclaw/skills/tech-updates-collector/output/
# 至少应有一个 YYYY-MM-DD.md 文件

# 如果 collector 尚未安装，请先参考:
# 5. F1-TechUpdate/README.md
```

### Step 3: 验证脚本可执行

```bash
# 测试监工虾（会因为没有当日数据而报告 P0 问题，这是正常的）
node skills/tech-updates-writer/scripts/supervisor.js 2026-03-16
```

### Step 4: 配置 GitHub 发布（publish-config.json）

```bash
# 编辑发布配置
vi skills/tech-updates-writer/publish-config.json

# 必须修改的字段：
# - github.remoteUrl: 改为你的 GitHub 仓库地址
# - auth.method: 选择 ssh 或 pat
# - auth.sshKeyPath: 如使用 SSH，确认密钥路径正确

# 验证认证：
# SSH 方式
ssh -T git@github.com

# PAT 方式（需设置环境变量）
# export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# 确认本地 clone 目录存在
ls /tmp/jason.xue  # 或 publish-config.json 中配置的 localCloneDir
```

### Step 5: 初始化 state.json

首次安装时 `state.json` 已初始化为带 checkpoint 的状态机结构：

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

Orchestrator Agent 首次在触发时间窗口内会自动启动执行。详见 `ORCHESTRATOR.md`。

---

## 5. HEARTBEAT.md 定时任务配置

在 OpenClaw 的 `HEARTBEAT.md` 中添加以下段落（幂等）。先检查是否已存在：

```bash
HEARTBEAT_FILE="$HOME/.openclaw/HEARTBEAT.md"
if grep -q "虾群协作写作系统" "$HEARTBEAT_FILE" 2>/dev/null; then
  echo "✔ 虾群协作写作系统任务已存在，跳过写入"
else
  cat >> "$HEARTBEAT_FILE" << 'EOF'

## 虾群协作写作系统 📝 (daily at Beijing 15:00 / UTC 07:00)
If current time >= UTC 07:00:
- 读取 `skills/tech-updates-writer/state.json`
- 判断是否需要执行:
  - `lastWritingSystemCheck` 不是今天 AND `currentRun.status` != "running" → 启动 Orchestrator
  - `currentRun.status` == "failed" AND `totalRetries` < 3 → 从断点恢复（重启 Orchestrator）
  - `currentRun.status` == "running" → 跳过（Orchestrator 正在工作）
  - `currentRun.status` == "paused" → 跳过（等待人工介入，发送提醒）
  - `currentRun.status` == "completed" → 跳过（今天已完成）
- 启动方式: 使用 sessions_spawn 创建 Orchestrator Agent
  - Orchestrator 定义: `skills/tech-updates-writer/ORCHESTRATOR.md`
  - Phase 具体逻辑: `skills/tech-updates-writer/SKILL.md`
  - 传入当天日期，Orchestrator 独立运行，主 Agent 不阻塞
- 更新 state.json: `currentRun.status` = "running", `orchestratorStartTime` = now

## 写作系统看门狗 🐕 (hourly, UTC 08:00-16:00)
Quick check (< 1 minute):
- 读取 `skills/tech-updates-writer/state.json` → `currentRun`
- 如果 `status` == "running" 且 `orchestratorStartTime` 距今 > 3 小时:
  - 判定为僵死，标记 `status` = "failed"
  - 发送告警: "Orchestrator 超过 3 小时无响应，已标记失败"
- 如果 `status` == "failed" 且 `totalRetries` < 3:
  - 下次 HEARTBEAT 检查时会自动从断点重启 Orchestrator
- 如果 `status` == "paused":
  - 发送提醒给 human（每 2 小时提醒一次，最多 3 次）
  - 内容: "写作系统在 Phase {N} 暂停，需要人工介入，原因: {error}"
EOF
  echo "✔ 虾群协作写作系统任务已写入 $HEARTBEAT_FILE"
fi
```

**触发机制说明**：
- OpenClaw 的 `startHeartbeatRunner` 按配置间隔读取 HEARTBEAT.md
- 主 Agent 检查 `state.json` 中的 `currentRun.status` 决定行为
- 启动 Orchestrator 后主 Agent 立即释放，继续处理其他任务
- 看门狗每小时检查 Orchestrator 健康状态
- Orchestrator 崩溃后，看门狗标记 failed，下次 HEARTBEAT 自动恢复

**与 collector 的执行顺序**：
- collector 每小时执行一次，通常在 writer 触发前已有当日日报
- 如果 Orchestrator 启动时日报不存在，Phase 0 会标记失败并等待重试
- 建议在 HEARTBEAT.md 中将 collector 段落放在 writer 之前

---

## 6. 工作流概览

```
HEARTBEAT.md 触发 (UTC 07:00)
  → 主 Agent 检查 state.json
  → sessions_spawn 启动 Orchestrator Agent
  → 主 Agent 释放（继续处理其他任务）

Orchestrator Agent 独立执行:
  → 读取 state.json，确定起点（全新 or 断点恢复）
  → 启动实时监控: node scripts/monitor-launcher.js &
  → Phase 0: 定位最新日报 → 生成话题池（去重）
  │   └── checkpoint: phase 0 completed
  → Phase 1: 编辑虾选题（评分 + 去重）
  │   └── checkpoint: phase 1 completed
  → Phase 2-4: 流水线模式（7 批 × 3 篇）
  │   Batch N: 创作 → 质量门禁 → 评审 → 修正(如需) → done
  │   Batch N+1:       创作 → 质量门禁 → 评审 → done
  │   ...（同时最多 2 个 Batch 执行）
  │   └── checkpoint: phase 2/3/4 completed + qualityGates 记录
  → Phase 5: 编辑虾最终选择 7 篇（时效性强制检查）
  → Phase 6: 发布虾评估（>90 分发布）
  → Phase 7: 发布到 GitHub Pages
  → Phase 8: 生成总结报告 → 发送 Feishu
  → Phase 9: 更新选题文件（供明天去重）
  → Phase 10: 监工虾质量检查（确认性检查）
  → 更新 state.json: status = "completed"

任何 Phase 失败:
  → 自动重试（最多 3 次）
  → 3 次仍失败 → status = "paused"，告警，等待人工介入
  → 主 Agent 看门狗每小时检查健康状态

主 Agent 看门狗 (每小时 UTC 08:00-16:00):
  → 读取 state.json
  → Orchestrator 运行 > 3 小时 → 判定僵死 → 标记 failed
  → status == "failed" → 下次 HEARTBEAT 自动重启 Orchestrator（断点恢复）
  → status == "paused" → 提醒 human
```

---

## 7. 监控脚本说明

### supervisor.js — 监工虾

事后全面质量检查，检查 Phase 1-7 的执行质量：

```bash
# 检查今天
node scripts/supervisor.js

# 检查指定日期
node scripts/supervisor.js 2026-03-16

# 只检查特定 Phase
node scripts/supervisor.js --phases=4,5
```

输出：`supervisor-report-YYYY-MM-DD.json` + `.md`

### realtime-supervisor.js — 实时监控虾

执行期间每 10 分钟检查进度，发现 P0 问题立即告警：

```bash
node scripts/realtime-supervisor.js
```

### monitor-launcher.js — 监控启动器

组合启动实时监控 + 告警检查：

```bash
node scripts/monitor-launcher.js &
```

### notification-helper.js — 通知助手

读取监控脚本生成的通知文件并输出：

```bash
node scripts/notification-helper.js
```

详细用法参考 `docs/SUPERVISOR-GUIDE.md` 和 `docs/REALTIME-MONITOR-GUIDE.md`。

---

## 8. 常见问题

| 问题 | 排查方法 |
|------|----------|
| Phase 0 报日报不存在 | 确认 `../tech-updates-collector/output/` 目录下有 `.md` 文件；如为空，先运行 `tech-updates-collector` |
| Phase 0 警告日报过期 | 最新日报修改时间超过 48 小时，建议先触发一次 collector 采集更新 |
| 监工虾路径错误 | 检查 `WRITER_BASE_DIR` 环境变量，或确认从 Skill 根目录运行 |
| Phase 4 换话题（P0） | Phase 4 内嵌质量门禁会自动丢弃 v2 并保留 v1；如仍出现，检查门禁阈值 |
| Phase 5 时效性评分错误（P0） | 检查评分逻辑是否严格按年份打分 |
| GitHub push 失败 | 检查 `publish-config.json` 认证配置；SSH 方式运行 `ssh -T git@github.com`，PAT 方式检查 `GITHUB_TOKEN` 环境变量 |
| state.json 不更新 | 检查文件写入权限；如损坏，从 state.json.bak 恢复 |
| Orchestrator 超时 | 看门狗会在 3 小时后标记 failed；检查是否有 Phase 卡住；查看实时监控输出 |
| Orchestrator 启动后立即退出 | 检查 state.json 是否可读；检查 currentRun.status 是否为 "completed" |
| 断点恢复后重复执行 | 检查 checkpoints 中对应 Phase 的 status 是否正确标记为 "completed" |
| 主 Agent 被写作系统占满 | 确认 HEARTBEAT.md 使用的是 sessions_spawn 委托模式，而非主 Agent 直接执行 |

---

**版本**: v2.0 (Orchestrator 架构)
**更新时间**: 2026-03-19
