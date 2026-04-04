# Claw Manager — OpenClaw 任务神经系统

> **定位**：以守护进程方式监控 OpenClaw 所有长时任务（Orchestrator、视频渲染、发布流水线），
> 自动检测崩溃、诊断原因、决策重启，并通过本地 Dashboard + 飞书告警呈现状态。
>
> **安装目录**：`~/.openclaw/claw-manager/`
> **systemd service**：`~/.config/systemd/user/claw-manager.service`
> **本地 API**：`http://localhost:17890`

---

## 一、文件清单

| 文件 | 说明 |
|------|------|
| `daemon.py` | 守护进程核心（30 秒轮询、资源监控、崩溃检测、重启决策、Dashboard 生成、飞书告警） |
| `task_parser.py` | 任务注册工具（支持 LLM 提炼 + `--no-llm` 手动模式） |
| `claw-manager.service` | systemd user service 定义（MemoryMax=64M, CPUWeight=50） |
| `dashboard.html` | 暗色三栏 Dashboard（资源 / 任务看板 / 告警流），每轮轮询刷新 |
| `task_profiles.json` | 各 Skill 资源画像（峰值内存、平均时长、并发上限、重启策略） |
| `knowledge_base.json` | 故障模式库（规则匹配，不消耗 LLM） |
| `watch.json` | 当前监控任务列表（守护进程读写） |
| `state.json` | 守护进程每轮快照（系统资源 + 任务状态摘要） |
| `events.jsonl` | Append-only 事件流（各 Orchestrator 写入 + 守护进程写入） |
| `alerts.jsonl` | 告警记录（需要人类关注的事件子集） |
| `pids/<taskId>.json` | Session 子代理心跳文件（守护进程自动管理） |

---

## 二、安装部署（Agent 执行指导）

### 前置依赖

```bash
# Python 依赖（仅 psutil）
pip3 install psutil
```

### 步骤 1：确认文件存在

```bash
ls ~/.openclaw/claw-manager/
# 期望看到：daemon.py  task_parser.py  claw-manager.service  task_profiles.json  ...
```

### 步骤 2：安装 systemd service

service 文件需要放到 systemd user 目录，有两种方式：

**方式 A（推荐）：直接 enable 原路径**
```bash
systemctl --user enable ~/.openclaw/claw-manager/claw-manager.service
systemctl --user start claw-manager
```

**方式 B：复制到 systemd 目录**
```bash
mkdir -p ~/.config/systemd/user/
cp ~/.openclaw/claw-manager/claw-manager.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable claw-manager
systemctl --user start claw-manager
```

### 步骤 3：验证运行状态

```bash
systemctl --user status claw-manager --no-pager
# 期望：Active: active (running)
# 期望内存：< 20MB（目标恒定 ~12-15MB）
```

### 步骤 4：确认守护进程正常轮询

```bash
# 等 35 秒后检查（每 30 秒轮询一次）
sleep 35
python3 -c "import json; d=json.load(open('/home/ubuntu/.openclaw/claw-manager/state.json')); print('updated:', d['updated_at']); print('CPU:', d['resources']['cpu_pct'], '%  MEM:', d['resources']['mem_pct'], '%')"
```

### 常用运维命令

```bash
# 查看实时日志
journalctl --user -u claw-manager -f

# 重启（修改 daemon.py 后执行）
systemctl --user restart claw-manager

# 停止
systemctl --user stop claw-manager

# 取消开机自启
systemctl --user disable claw-manager

# 测试单轮 poll（不以 service 方式运行）
python3 ~/.openclaw/claw-manager/daemon.py --test-once
```

### 修改 service 配置

编辑 `~/.openclaw/claw-manager/claw-manager.service` 后执行：
```bash
systemctl --user daemon-reload
systemctl --user restart claw-manager
```

> ⚠️ 注意：`CPUQuota` 不设（arm64 上有兼容性问题），使用 `CPUWeight=50` 代替。
> `MemoryMax=64M` 是守护进程本身上限，截图等重型操作通过独立子进程执行，不计入此配额。

---

## 三、任务注册（Agent 执行指导）

### 注册本地进程任务（有 PID）

```bash
# 先启动任务，记录 PID
python3 some_script.py &
MY_PID=$!

# 注册到 claw-manager
python3 ~/.openclaw/claw-manager/task_parser.py \
  --label "video-orchestrator-0403" \
  --desc "制作 2026-04-03 的 7 篇文章视频" \
  --skill "article2video" \
  --pid $MY_PID \
  --state-file "~/.openclaw/skills/article2video/batch-state.json" \
  --no-llm
```

### 注册 OpenClaw 子代理任务（无本地 PID）

```bash
# sessions_spawn 返回 childSessionKey 后注册
python3 ~/.openclaw/claw-manager/task_parser.py \
  --label "weixin-publisher-0403" \
  --desc "发布 2026-04-03 的 7 篇文章到微信公众号" \
  --skill "weixin-publisher" \
  --session-key "agent:main:subagent:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --state-file "~/.openclaw/skills/weixin-publisher/state.json" \
  --no-llm
```

### task_parser.py 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--label` | ✅ | 任务显示名称（唯一标识用） |
| `--desc` | ✅ | 任务描述（用于 LLM 提炼，`--no-llm` 时可随意） |
| `--skill` | ❌ | Skill 名称（用于匹配 task_profiles.json 画像） |
| `--pid` | ❌ | 本地进程 PID（本地脚本任务用） |
| `--session-key` | ❌ | OpenClaw session key（子代理任务用） |
| `--state-file` | ❌ | 任务状态文件路径（用于 mtime 兜底检测） |
| `--no-llm` | ❌ | 跳过 LLM 提炼，直接注册（推荐，速度快） |

---

## 四、事件上报（Orchestrator/Agent 埋点格式）

各 Orchestrator 在关键节点写入 events.jsonl，守护进程读取后：
1. 更新任务状态
2. 自动刷新 session 子代理的心跳文件（触发存活检测续期）

### 最小上报格式

```bash
python3 -c "
import json, time
with open('/home/ubuntu/.openclaw/claw-manager/events.jsonl', 'a') as f:
    f.write(json.dumps({
        'ts': int(time.time()),
        'source': 'TASK_LABEL',   # 与注册时的 label 一致
        'event': 'phase_done',
        'phase': 'phase2',        # 当前完成的阶段名
        'detail': 'Phase 2 写作完成，7 篇文章生成'
    }) + '\n')
"
```

### 推荐的事件类型

| event 值 | 触发时机 |
|----------|----------|
| `task_start` | 任务/Orchestrator 启动时 |
| `phase_done` | 每个 Phase 完成时（兼做心跳） |
| `task_done` | 任务全部完成时 |
| `task_fail` | 任务遇到不可恢复错误时 |
| `heartbeat` | 长时间无 phase 完成时，定期上报保活 |

### Shell 一行版（适合在 bash Orchestrator 中嵌入）

```bash
echo '{"ts":'$(date +%s)',"source":"VIDEO_ORCH","event":"phase_done","phase":"phase3","detail":"Remotion 渲染完成"}' \
  >> ~/.openclaw/claw-manager/events.jsonl
```

---

## 五、子代理心跳机制

Session 子代理（无本地 PID）的存活由心跳文件驱动：

- 心跳文件路径：`~/.openclaw/claw-manager/pids/<taskId>.json`
- 守护进程每轮轮询时读取 events.jsonl 尾部新事件，自动更新心跳
- **无需子代理主动写心跳文件**，上报 phase_done 事件即可触发心跳续期

存活检测三层逻辑（优先级从高到低）：

1. **启动宽限期**：`startedAt` 后 5 分钟内，无条件视为存活
2. **本地 PID**：`os.kill(pid, 0)` 检查（本地进程专用）
3. **Session 心跳文件**：`lastHeartbeat` 在 `POLL_INTERVAL × 3`（90 秒）内 → 存活
4. **stateFile mtime**：文件修改时间在 `POLL_INTERVAL × 2`（60 秒）内 → 存活

---

## 六、Dashboard 使用

Dashboard HTML 每次守护进程轮询后自动重新生成：

```bash
# 本地浏览器打开
xdg-open ~/.openclaw/claw-manager/dashboard.html

# 通过本地 API 触发任务操作（重启/跳过）
curl -s http://localhost:17890/state | python3 -m json.tool
```

API 端点：
- `GET /state` — 返回当前 state.json 内容
- `POST /restart/<taskId>` — 手动触发任务重启
- `POST /skip/<taskId>` — 跳过任务（标记为 skipped）

---

## 七、文件格式规范

### watch.json（任务监控列表）
```json
{
  "tasks": [
    {
      "taskId": "video-orch-abc123",
      "label": "video-orchestrator-0403",
      "skill": "article2video",
      "status": "running",
      "pid": null,
      "sessionKey": "agent:main:subagent:xxx",
      "stateFile": "~/.openclaw/skills/article2video/batch-state.json",
      "startedAt": 1743760000,
      "estimatedMinutes": 120,
      "autoRestart": true,
      "maxRestarts": 3,
      "restartCount": 0,
      "successCriteria": "batch-state.json status=completed"
    }
  ],
  "queue": []
}
```

### state.json（守护进程快照）
```json
{
  "updated_at": "2026-04-04 14:30:00",
  "resources": {
    "cpu_pct": 3.2,
    "mem_pct": 37.1,
    "mem_available_mb": 9800,
    "remotion_instances": 0
  },
  "tasks": [ ... ]
}
```

### events.jsonl / alerts.jsonl（事件流）
每行一个 JSON，Append-only：
```json
{"ts": 1743760000, "source": "video-orch", "event": "phase_done", "phase": "phase3", "detail": "渲染完成"}
{"ts": 1743760060, "event": "crash_detected", "taskId": "video-orch-abc", "detail": "OOM_LIKELY: 内存 85%"}
```

---

## 八、11小分队 — 队员角色系统

Claw Manager v2 引入了"11小分队"角色系统（`SKILL_PROFILES` 字典），将每个 Skill 拟人化为固定队员，赋予独特个性和职责。

### 队员列表

| 队员 | Emoji | 角色 | 对应 Skill |
|------|-------|------|----------|
| **Scout** | 🔍 | 情报官 | `tech-updates-collector` |
| **Quill** | ✍️ | 主笔 | `tech-updates-writer` |
| **Frame** | 🎬 | 导演 | `article2video` |
| **Echo** | 📢 | 运营 | `channels-publisher` / `weixin-publisher` |
| **Forge** | 🔧 | 工程师 | `kiro-cli` |
| **Warden** | 🛡️ | 守卫 | `claw-manager`（常驻） |

### SKILL_PROFILES 数据结构

`daemon.py` 中的 `SKILL_PROFILES` 字典为每位队员定义了：

```python
SKILL_PROFILES = {
    "Scout": {
        "emoji": "🔍",
        "cn": "情报官",           # 中文角色名
        "en": "Scout",
        "skill": "tech-updates-collector",  # 对应 Skill 名称
        "desc": "全网 AI 资讯采集简介...",   # Skill 简介
        "phases": [               # 执行环节列表 (name, level)
            ("维度 A-G 搜索", "normal"),
            ("日报写入", "normal"),
        ],
        "state_file": "~/.openclaw/skills/tech-updates-collector/output/",
        "achievements_check": "collector"  # 成就检查标识
    },
    # ... 其余队员
}
```

### Skill 档案页

Dashboard 左栏显示 11小分队 Org Chart，**点击队员卡片**后，中栏切换为该队员的 Skill 档案页，包含：

- **简介**：Skill 定位与能力描述
- **执行环节**：各 Phase 列表，高风险环节标注 `⚠️ 高风险`
- **近7天统计**：从 `watch.json` + `events.jsonl` 动态计算的运行次数、成功率、平均耗时
- **成就**：基于历史数据计算的里程碑成就（如"百篇产出"、"连续成功"等）

---

## 九、watch.json 完整 Schema（v0.4）

watch.json 在原有字段基础上扩展了以下新字段（`task_parser.py` v2 支持写入）：

```json
{
  "tasks": [
    {
      "taskId": "tech-writer-orchestrator-0404-4a8132",
      "label": "Quill: 4/4 虾群协作写作",
      "skill": "tech-updates-writer",
      "status": "running",

      "assignedTo": "Quill",
      "goal": "在2026-04-04 23:59前完成21篇AI资讯v2文章（评分≥80），发表7篇均分≥85",
      "project": "daily-content-pipeline",
      "date": "2026-04-04",

      "dependsOn": ["collector-0404"],

      "batchProgress": {
        "total": 21,
        "completed": 7,
        "failed": 0
      },

      "cost": {
        "tokens_in": 45000,
        "tokens_out": 12000,
        "usd": 0.315,
        "budget_usd": 30.0
      },

      "result": "✅ 21篇初稿 → 7篇发表，均分86.3，Phase 0-10全部完成",

      "pid": null,
      "sessionKey": "agent:main:subagent:xxx",
      "stateFile": "~/.openclaw/skills/tech-updates-writer/state.json",
      "startedAt": 1775287573,
      "estimatedMinutes": 220,
      "autoRestart": true,
      "maxRestarts": 2,
      "restartCount": 1,
      "successCriteria": "7篇发表，均分≥85"
    }
  ],
  "queue": []
}
```

### 新字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `assignedTo` | string | 负责的队员名称（对应 `SKILL_PROFILES` 的 key，如 `Scout`、`Quill`） |
| `goal` | string | SMART 格式的任务目标（含具体时间、可量化指标） |
| `project` | string | 所属流水线（`daily-content-pipeline` / `video-pipeline` / `infra`） |
| `date` | string | 北京时间日期，格式 `YYYY-MM-DD` |
| `dependsOn` | array | 依赖的 `taskId` 列表，甘特图据此绘制依赖箭头 |
| `batchProgress` | object | 批处理进度 `{total, completed, failed}` |
| `cost` | object | 成本追踪 `{tokens_in, tokens_out, usd, budget_usd}` |
| `result` | string | 任务完成后的结果摘要（`task_done` 或 `task_fail` 时写入） |

### task_parser.py 新增参数（v2）

```bash
python3 ~/.openclaw/claw-manager/task_parser.py \
  --label "Quill: 4/4 虾群协作写作" \
  --desc "完成21篇AI资讯文章" \
  --skill "tech-updates-writer" \
  --session-key "agent:main:subagent:xxx" \
  --assigned-to "Quill" \
  --goal "在2026-04-04 23:59前完成21篇AI资讯v2文章（评分≥80），发表7篇均分≥85" \
  --project "daily-content-pipeline" \
  --depends-on "collector-0404" \
  --date "2026-04-04" \
  --budget-usd 30.0 \
  --no-llm
```

---

## 十、Dashboard v2 功能说明

Dashboard v2 采用 **GitHub Dark + Linear 质感**配色方案（`#0d1117` 背景、`#161b22` 卡片、`#58a6ff` 强调色），全面重设计。

### 整体布局

```
┌─────────────────────────────────────────────────────────────┐
│  顶部状态栏（40px）  CPU% | MEM% | DISK% | 今日统计 | 时间戳   │
├──────────┬──────────────────────────────┬────────────────────┤
│  左栏    │  中栏（flex）                │  右栏（260px）     │
│  220px   │                              │                    │
│  11小分队 │  按日期分组的任务看板        │  🚨 告警            │
│  Org Chart│  或 Skill 档案页（点击切换）│  📋 彩色事件流      │
│          │                              │                    │
├──────────┴──────────────────────────────┴────────────────────┤
│  底部：甘特时间线（全宽）                                       │
│  [横轴时间线] [任务条] [子模块进度] [依赖箭头]                   │
└─────────────────────────────────────────────────────────────┘
```

### 各区域说明

#### 顶部状态栏（40px 高）
- **系统资源**：CPU% / MEM% / DISK% 实时数值（彩色渐变，超阈值变红）
- **今日统计**：完成任务数 / 运行中 / 队列中 / 失败数
- **时间戳**：最后更新时间 + 倒计时刷新

#### 左栏：11小分队 Org Chart（220px）
- 标题"11小分队"，6 位队员竖排显示
- 每个队员卡片：emoji + 角色名 + 状态徽章（今日是否有任务运行）
- **点击卡片** → 中栏切换为该队员的 Skill 档案页
- Warden（守卫）常驻标注，指示 Claw Manager 本身的健康状态

#### 中栏：任务看板 / Skill 档案页
**默认视图 — 任务看板**：
- 按 `date` 字段分组展示（今日 / 昨日 / 更早）
- **所有状态任务全部显示**（修复了旧版只显示 running 的 bug）
- 每个任务卡片包含：队员标签 + 进度条（`batchProgress`）+ 操作按钮（重启/跳过）
- `running` 状态任务进度条带 `@keyframes pulse-bar` 脉冲动效

**Skill 档案页**（点击左栏队员后切换）：
- Skill 简介 + 执行环节（高风险标注）
- 近7天统计：运行次数 / 成功率 / 平均耗时
- 成就展示

#### 右栏：告警 + 事件流（260px）
- **未解决告警**：红色高亮 + 操作按钮（确认/重启）
- **彩色事件流**：最近 50 条事件，按类型染色：
  - `phase_done` → 绿色
  - `task_fail` / `crash_detected` → 红色
  - `task_start` / `task_registered` → 蓝色
  - `heartbeat` → 灰色

#### 底部：甘特时间线（全宽）
- **横轴**：动态时间轴（按所有任务的 `startedAt` / `endTime` 计算范围）
- **任务条**：每个任务一行，颜色区分状态（done=绿 / failed=红 / running=蓝脉冲 / queued=灰）
- **子模块展开**：展开后显示 `batchProgress` 中各子模块的进度条
- **依赖箭头**：基于 `dependsOn` 字段，在任务条之间绘制依赖箭头

---

## 十一、事件上报规范（v2 含成本字段）

### 基础格式（同 v1）

```bash
echo '{"ts":'$(date +%s)',"source":"TASK_LABEL","event":"phase_done","phase":"phase2","detail":"写作完成"}' \
  >> ~/.openclaw/claw-manager/events.jsonl
```

### 带成本字段的上报格式（v2 新增）

Orchestrator 在每个 Phase 完成时附带 token 消耗，daemon.py 会自动累加到 `watch.json` 的 `cost` 字段：

```json
{
  "ts": 1775287573,
  "event": "phase_done",
  "source": "tech-writer-orchestrator-0404",
  "phase": "phase2",
  "detail": "Phase 2 写作完成，21篇初稿生成",
  "cost_tokens_in": 45000,
  "cost_tokens_out": 12000,
  "model": "claude-sonnet-4-6"
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `cost_tokens_in` | 本次 Phase 消耗的输入 token 数 |
| `cost_tokens_out` | 本次 Phase 消耗的输出 token 数 |
| `model` | 使用的模型名称（用于匹配定价表换算 USD） |

### 模型定价表（来自 task_profiles.json）

daemon.py 读取 `task_profiles.json` 中的 `model_pricing` 进行 token → USD 换算：

| 模型 | 输入（$/M tokens） | 输出（$/M tokens） |
|------|-------------------|-------------------|
| `claude-sonnet-4-6` | $3.00 | $15.00 |
| `claude-opus-4-6` | $15.00 | $75.00 |
| `claude-haiku-3-5` | $0.80 | $4.00 |
| `claude-sonnet-4-20250514` | $3.00 | $15.00 |
| `gpt-4o` | $5.00 | $15.00 |

汇率：1 USD = 7.25 CNY

---

*最后更新：2026-04-04（v0.4 实现完成）*
