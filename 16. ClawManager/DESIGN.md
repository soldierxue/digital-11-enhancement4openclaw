# Claw Manager — 设计文档 v0.4

> **目标**：从主会话对话中提炼人类任务，主动跟踪执行状态，无需人类询问进展。
> **定位**：OpenClaw 的任务神经系统——感知、调度、自愈、进化。
> **核心约束**：自身资源消耗必须恒定，与任务数量无关；不能成为系统瓶颈。
>
> 版本：v0.4
> 日期：2026-04-04（Dashboard 展示方案确认 + 一键重启设计 + 重启决策策略确认）
> 作者：Digital11

---

## 一、宿主机资源实测（2026-04-04）

### 1.1 硬件配置
```
总内存：15.7 GB
可用内存（当前）：~8 GB
Swap：2 GB
磁盘总量：96 GB，已用 49 GB（51%）
```

### 1.2 各进程实测内存占用

| 进程 | 内存 | 说明 |
|------|------|------|
| openclaw-gateway | **1,398 MB** | 主进程，常驻 |
| openclaw-tui | 502 MB | 终端 UI |
| Remotion 渲染（每个实例） | **476 MB × 5** = 2,380 MB | 视频渲染，峰值 |
| Chromium（浏览器） | 473 + 350 + 336 MB = 1,159 MB | 视频号/公众号发布 |
| gnome-shell | 416 MB | 桌面 |
| xdg-desktop-portal | 356 MB | 桌面服务 |
| LiteLLM | 306 MB | 模型代理 |
| node | 301 MB | 各类工具 |

**实测峰值场景（视频渲染中）**：
```
常驻基础服务：1,398 + 502 + 416 + 356 + 306 + 301 ≈ 3,279 MB
Remotion 渲染（5实例并发）：476 × 5 ≈ 2,380 MB
Chromium（发布时）：1,159 MB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
峰值合计：≈ 6,818 MB
可用缓冲：15,700 - 6,818 ≈ 8,882 MB
```

**关键发现**：15.7GB 内存的机器，视频渲染+发布同时运行是完全安全的。之前 4 次 OOM 是因为 Remotion 同时运行了 **5个实例**（2,380 MB），叠加 kiro-cli/Python 子代理的内存，**不是内存不足，而是并发控制缺失**。

### 1.3 Claw Manager 自身资源需求重新评估

| 组件 | 预估内存 | 说明 |
|------|---------|------|
| daemon.py（Python 守护进程） | **25-40 MB** | 轮询 + 事件处理，无大对象 |
| HTML Dashboard 生成 | **0 MB 常驻** | 按需生成，生成后写文件 |
| Task Parser（LLM调用） | 不计入常驻 | 只在注册时调用，用完释放 |

**修正**：之前 `MemoryMax=50MB` 太激进，**修正为 `MemoryMax=128MB`**，给足缓冲。  
CPU 配额维持 `CPUQuota=5%`，完全够用（轮询检查全是 I/O 等待，不是 CPU 计算）。

---

## 二、自动重启决策逻辑（核心升级）

### 2.1 重启前三步判断

```
任务崩溃检测到 → 不立即重启
               ↓
  Step 1: 诊断崩溃原因
  Step 2: 评估当前资源是否满足
  Step 3: 判断是否满足重启条件
               ↓
  满足 → 自动重启（记录日志）
  不满足 → 入任务队列 + 通知用户介入
```

### 2.2 崩溃原因诊断（规则驱动，不消耗LLM）

```python
def diagnose_crash(task, event):
    signals = collect_signals(task)
    
    # 信号1：OOM killer 触发
    if check_oom_killed(task.pid):
        return CrashReason.OOM, "OOM killer 终止了进程"
    
    # 信号2：内存飙升后进程消失
    if signals.mem_before_crash > 80 and event.type == "subagent_died":
        return CrashReason.OOM_LIKELY, "崩溃前内存 > 80%，疑似OOM"
    
    # 信号3：已知错误模式匹配（从知识库）
    for pattern in knowledge_base.patterns:
        if pattern.matches(signals.last_log_line):
            return CrashReason.KNOWN_ERROR, pattern
    
    # 信号4：今日重启次数过多
    if task.restart_count_today >= 3:
        return CrashReason.REPEATED_CRASH, "今日已重启3次"
    
    # 信号5：超时（正常退出，任务卡住）
    if event.type == "stall" and task.runtime > task.max_runtime:
        return CrashReason.STALL, "超时卡住"
    
    return CrashReason.UNKNOWN, "原因未知"
```

### 2.3 资源可行性评估

```python
def assess_resources(task):
    current = get_system_resources()
    
    # 查任务画像（历史实测数据）
    profile = task_profiles.get(task.skill)
    required_mem = profile.peak_memory_mb if profile else estimate_memory(task)
    
    # 评估结果
    available_mem = current.total_mem - current.used_mem
    
    if available_mem < required_mem * 1.3:  # 30% 安全缓冲
        return ResourceAssessment.INSUFFICIENT, f"可用内存 {available_mem}MB < 需要 {required_mem * 1.3:.0f}MB"
    
    # 并发检查：Remotion 实例数
    remotion_count = count_running_remotion_instances()
    if task.skill == "article2video" and remotion_count >= 3:
        return ResourceAssessment.CONCURRENT_LIMIT, f"已有 {remotion_count} 个 Remotion 实例在运行"
    
    return ResourceAssessment.OK, f"可用内存 {available_mem}MB 充足"
```

### 2.4 重启决策表

| 崩溃原因 | 资源充足 | 决策 | 动作 |
|---------|---------|------|------|
| OOM（已知） | ✅ 是 | 自动重启 | 重启前 `sync && echo 3 > /proc/sys/vm/drop_caches` 释放缓存 |
| OOM（已知） | ❌ 否 | 排队等待 | 入队 + 通知用户：资源不足，预计等待 XX 分钟 |
| OOM 疑似 | ✅ 是 | 自动重启（1次） | 超过 1 次则通知用户 |
| 已知错误 + 已知修复 | 任意 | 应用修复后重启 | 如 IP白名单错误 → 停止，通知人类 |
| 重启次数 ≥ 3 | 任意 | 停止，通知人类 | "已连续失败 3 次，需要人工介入" |
| 超时卡住 | ✅ 是 | 自动重启（断点恢复） | 从上次检查点继续 |
| 原因未知 | 任意 | 停止，通知人类 | 附带所有已收集信号供诊断 |

### 2.5 任务队列

当资源不足时，任务不是直接失败，而是进入队列等待：

```json
{
  "queue": [
    {
      "taskId": "video-0403-r4",
      "enqueuedAt": 1743760000,
      "reason": "内存不足：可用 3.2GB，需要 2.5GB × 1.3",
      "waitCondition": "mem_available > 3300",
      "maxWaitMin": 60,
      "notifiedUser": true
    }
  ]
}
```

守护进程每次 poll 时检查队列：条件满足则自动出队启动，超过 `maxWaitMin` 则告警升级。

---

## 三、HTML Dashboard 设计

### 3.1 定位
静态 HTML 文件，守护进程定期重新生成（每次 state.json 更新时触发）。  
不需要 HTTP server，直接用浏览器打开本地文件，或通过 OpenClaw 的 canvas 功能展示。

**文件路径**：`~/.openclaw/claw-manager/dashboard.html`

### 3.2 视觉设计规范

```
配色：暗色主题（#1a1a2e 背景，#16213e 卡片，#0f3460 高亮）
字体：系统无衬线字体
布局：三栏 Grid（资源 | 任务状态 | 告警&事件）
刷新：meta refresh 30秒自动刷新
```

### 3.3 Dashboard 布局草图

```
┌─────────────────────────────────────────────────────────────────┐
│  🔮 Claw Manager                          2026-04-04 12:45:32   │
│  Last updated 8 seconds ago                            [Refresh] │
├──────────────────┬──────────────────────┬───────────────────────┤
│  🖥️ 资源监控      │  📋 任务看板          │  🚨 告警 & 事件       │
│                  │                      │                       │
│  CPU  ████░░ 45% │  ✅ 今日完成 5        │  ⚠️ video-0403        │
│  内存 ████░░ 62% │  🔄 运行中  2        │  今日重启4次           │
│  磁盘 ████░░ 51% │  ⏸️ 队列中  0        │  疑似OOM循环          │
│                  │  ❌ 失败    1        │  建议：检查并发数      │
│  Peak 今日       │                      │                       │
│  CPU: 87%        │  ─────────────────── │  ❌ weixin-0403       │
│  内存: 78%       │  🔄 video-0403       │  IP白名单错误 40164   │
│                  │  5/7  ████████░░     │  需要人工添加IP       │
│  磁盘 I/O        │  运行 90min ETA 80min│                       │
│  读 2.3 MB/s     │  ⚠️ 今日第4次        │  ──────────────────── │
│  写 1.1 MB/s     │                      │  📋 最近事件          │
│                  │  🔄 data-collector   │  12:44 video重启(r3)  │
│                  │  定时任务 下次13:00  │  11:13 video重启(r2)  │
│                  │                      │  10:03 视频号草稿完成 │
│                  │  ❌ weixin-0403      │  09:34 video重启(r1)  │
│                  │  等待IP白名单确认    │                       │
│                  │                      │                       │
├──────────────────┴──────────────────────┴───────────────────────┤
│  📚 知识库命中                                                   │
│  video-oom-001（第6次命中）: Remotion 并发过高 → 建议限制≤3实例  │
│  today: 今日故障4次 → 触发「重复崩溃」模式，已升级到人工介入     │
├─────────────────────────────────────────────────────────────────┤
│  📊 今日任务时间线                                               │
│  20:00 ──────── writing ──────────────── 23:42 ✅               │
│  22:09 ── video[1] ── ✗ 23:02           重启1                   │
│  09:34 ── video[2] ── ✗ 09:50           重启2                   │
│  11:13 ──── video[3] ──────────── ✗     重启3                   │
│  12:45 ──── video[4] ──────────────>    进行中                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 HTML 生成机制

守护进程使用 Python 的 `string.Template` 生成纯静态 HTML（不依赖任何模板引擎）：

```python
def generate_dashboard(state):
    # 生成任务卡片 HTML
    task_cards = "".join(render_task_card(t) for t in state.tasks)
    
    # 生成时间线 SVG
    timeline_svg = render_timeline_svg(state.events_today)
    
    # 生成资源仪表盘
    resource_gauges = render_gauges(state.resources)
    
    # 填充模板
    html = DASHBOARD_TEMPLATE.substitute(
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        resource_gauges=resource_gauges,
        task_cards=task_cards,
        alerts=render_alerts(state.alerts),
        timeline=timeline_svg,
        knowledge_hits=render_knowledge_hits(state.kb_matches)
    )
    
    # 原子写入
    write_atomic(DASHBOARD_PATH, html)
```

**关键**：生成 HTML 是纯 CPU 字符串操作，< 50ms，不需要网络，不需要数据库。

### 3.5 展示方式（已确认：本地浏览器 + 飞书告警 + localhost API 一键操作）

**资源消耗对比（选型依据）**：

| 方案 | 常驻内存 | CPU | 网络依赖 | 可靠性 | 交互支持 |
|------|---------|-----|---------|--------|---------|
| 本地浏览器 ✅ | 0（仅开时 ~500MB） | 0 常驻 | 无 | ⭐⭐⭐⭐⭐ | ✅ 完整 |
| OpenClaw Canvas | 0 | 0 常驻 | 依赖 Gateway | ⭐⭐⭐⭐ | ⚠️ 受限 |
| 飞书截图 | 0 | 截图时瞬时 | 需要飞书 API | ⭐⭐⭐ | ❌ 图片不可交互 |

**Canvas 方案的致命问题**：Gateway 挂了也能看 Dashboard 恰恰是最需要 Dashboard 的时候——故障时最依赖它，可靠性反而倒退。

**✅ 确认方案：三层组合**

**层 1 — 主查询：本地浏览器**（零依赖，最可靠）
```bash
# 随时查看
xdg-open ~/.openclaw/claw-manager/dashboard.html
# Dashboard 内嵌 <meta http-equiv="refresh" content="30">，自动刷新
```

**层 2 — 主动推送：飞书告警截图**（异常不用主动去看）
```python
# 守护进程检测到告警时自动截图推送
screenshot = headless_screenshot(DASHBOARD_PATH)  # 用 headless Chromium，< 2 秒
feishu_send_image(screenshot, caption=f"⚠️ {alert.msg}")
```
仅在告警时触发，不常驻，不消耗资源。

**层 3 — 一键操作：localhost:17890 微型 API**（支持 Dashboard 按钮交互）
```python
# 守护进程内嵌极轻量 HTTP（仅监听 127.0.0.1，外部无法访问）
# 额外内存占用 < 5MB（Python http.server）
from http.server import HTTPServer, BaseHTTPRequestHandler

class TriggerHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        data = json.loads(self.rfile.read(...))
        # 支持的操作：restart / skip / pause / resume
        write_trigger(data["action"], data["taskId"])
        self.send_response(200)
```

Dashboard 中的操作按钮：
```html
<!-- 重启按钮 -->
<button class="btn-restart" onclick="trigger('restart', 'video-0403')">
  🔄 重启
</button>

<!-- 跳过当前任务 -->
<button class="btn-skip" onclick="trigger('skip', 'video-0403')">
  ⏭️ 跳过
</button>

<!-- 暂停队列 -->
<button class="btn-pause" onclick="trigger('pause_queue', null)">
  ⏸️ 暂停队列
</button>

<script>
async function trigger(action, taskId) {
  const res = await fetch('http://localhost:17890/trigger', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action, taskId})
  });
  if (res.ok) { location.reload(); }
  else { alert('操作失败，请检查守护进程状态'); }
}
</script>
```

守护进程在下一轮 poll（≤30 秒）处理 trigger，执行对应操作并更新 Dashboard。

---

## 四、系统架构（更新版）

```
┌──────────────────────────────────────────────────────────────────┐
│                      主会话 (Main Agent)                          │
│                                                                   │
│  [对话] → Task Parser(LLM, 注册时一次) → watch.json              │
│  [心跳] → 读 state.json 一行摘要 → 决策是否介入                   │
│  [告警] → 读 alerts.jsonl → 执行人工操作（如加IP白名单）          │
└─────────────────────┬───────────────────────────────────────────┘
                      │  文件 IPC（无网络，无 socket）
┌─────────────────────▼───────────────────────────────────────────┐
│               Claw Manager Daemon (systemd user service)         │
│               内存 ≤ 128MB │ CPU ≤ 5% │ 自动重启                 │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Poll Loop（单线程，30秒间隔，固定资源消耗）               │   │
│  │                                                            │   │
│  │  1. 读 watch.json                                          │   │
│  │  2. check_system_resources()  ← 所有任务共享一次检查       │   │
│  │  3. for task in running_tasks:                             │   │
│  │       diagnose_if_crashed()   ← 规则引擎，无LLM           │   │
│  │       assess_resources()      ← 对照任务画像               │   │
│  │       decide_restart_or_queue()                            │   │
│  │  4. process_queue()           ← 检查等待条件               │   │
│  │  5. atomic_write(state.json)                               │   │
│  │  6. generate_dashboard.html   ← 按需重新生成               │   │
│  │  7. if alerts: notify_feishu()                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │  Task Profiles │  │  Task Queue  │  │  Knowledge Base     │  │
│  │  (历史画像)     │  │  (等待队列)  │  │  (故障模式库)       │  │
│  │  peak_mem      │  │  wait_cond   │  │  pattern matching   │  │
│  │  avg_duration  │  │  max_wait    │  │  auto evolve        │  │
│  └────────────────┘  └──────────────┘  └─────────────────────┘  │
└─────────────────────┬───────────────────────────────────────────┘
                      │ 文件 IPC
┌─────────────────────▼───────────────────────────────────────────┐
│                   子代理 / Skills                                 │
│                                                                   │
│  执行任务 → 每个 Phase 完成后：                                   │
│    echo '{"ts":..., "event":"phase_done", ...}' >> events.jsonl  │
│                                                                   │
│  各 Skill state.json 保持不变，守护进程读取但不修改              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 五、任务画像（Task Profiles）

基于实测数据建立，供资源评估使用：

```json
{
  "profiles": {
    "article2video": {
      "peak_memory_mb": 2400,
      "avg_duration_min": 38,
      "concurrent_limit": 3,
      "notes": "Remotion 5实例并发时峰值 ~2400MB，建议限制≤3实例",
      "pre_checks": ["mem_available > 3000", "remotion_instances < 3"],
      "pre_actions": ["drop_caches"]
    },
    "weixin-publisher": {
      "peak_memory_mb": 600,
      "avg_duration_min": 8,
      "concurrent_limit": 1,
      "notes": "依赖 Chromium，与 channels-publisher 不可同时运行",
      "pre_checks": ["weixin_api_accessible", "ip_whitelist_valid"],
      "pre_actions": ["verify_access_token"]
    },
    "channels-publisher": {
      "peak_memory_mb": 600,
      "avg_duration_min": 15,
      "concurrent_limit": 1,
      "notes": "依赖 Chromium，网络错误300333需重试",
      "pre_checks": ["chromium_available"]
    },
    "writing-system": {
      "peak_memory_mb": 400,
      "avg_duration_min": 220,
      "concurrent_limit": 1,
      "notes": "长任务，运行时不建议启动其他重型任务",
      "pre_checks": ["litellm_healthy", "model_available"]
    }
  }
}
```

---

## 六、资源目标与告警阈值（修订）

| 资源 | 健康区间 | 告警阈值 | 紧急阈值 | 动作 |
|------|---------|---------|---------|------|
| CPU | 50-70% | >80% | >90% | 暂停低优先级任务 |
| 内存 | 50-70% | >75% | >85% | 拒绝新任务入队，通知用户 |
| 磁盘 | <65% | >70% | >80% | 清理临时文件，通知用户扩容 |
| Remotion 实例数 | ≤3 | =4 | ≥5 | 限制并发，排队等待 |

**当前状态评估**：
- 内存 62%：✅ 健康区间
- 磁盘 51%：✅ 充裕
- Remotion 5实例：⚠️ 超出建议并发数（≤3），这就是OOM的真实原因

---

## 七、实现路线图（修订）

### Phase 0：OOM预防立即修复（今天可做）
修改 VIDEO-ORCHESTRATOR.md：渲染前检查 Remotion 实例数 ≤ 3，否则等待后再启动。  
这是今天反复崩溃的根本原因，一行检查可以解决。

### Phase 1：事件埋点（本周）
在各 Orchestrator 中加入 `echo >> events.jsonl` 追加。  
建立 `~/.openclaw/claw-manager/` 目录结构和文件格式。

### Phase 2：守护进程 MVP（1-2周）
- `daemon.py`：轮询 + 规则引擎 + 基础重启决策
- `task_profiles.json`：任务画像（基于实测填写）
- `knowledge_base.json`：故障模式初始化（填入本周已知故障）
- systemd user service
- **HTML Dashboard 基础版**（资源 + 任务状态 + 告警三栏）

### Phase 3：Task Parser + 队列调度（2-4周）
- `sessions_spawn` 后自动提炼任务
- 任务队列 + 等待条件评估
- Dashboard 增加时间线视图

### Phase 4：知识进化（持续）
- 故障模式自动匹配和积累
- 任务画像自动更新（每次任务完成后记录实测数据）
- 优化建议生成

---

## 八、任务捕获覆盖率分析

### 8.1 各任务入口的可见性

| 触发方式 | 可捕获 | 原因 |
|---------|--------|------|
| `sessions_spawn` 子代理 | ✅ 完整 | 有明确的 spawn 事件可 hook |
| Cron Job | ✅ 完整 | Cron 最终也通过 spawn 启动 |
| Swarm（多子代理协作） | ✅ 完整 | 每个 swarm 成员都是一次 spawn |
| Heartbeat 触发的子代理 | ✅ 完整 | 心跳内的 sessions_spawn 同样可 hook |
| **Heartbeat 内联操作** | ❌ 盲区 | 直接 exec/读文件，没有 spawn 边界 |
| **Skill 内联执行** | ❌ 盲区 | Skill 在主会话内运行，工具调用无独立进程 |
| **用户即时请求**（查天气等）| ❌ 盲区 | 主会话直接响应，< 5 秒，无需监控 |
| **主会话直接操作**（git/文件）| ❌ 盲区 | 同上，即时完成 |

### 8.2 覆盖率评估

```
当前设计假设：任务 = sessions_spawn 的子代理

实际分布（按需要监控的程度）：
  ├── 高优先级（长时运行、有状态）→ 几乎都是 spawn 类 ✅ 可捕获
  │    ├── 视频制作（40-90分钟）
  │    ├── 写作系统（2-3小时）
  │    ├── 公众号/视频号发布（10-30分钟）
  │    └── 数据采集（5-15分钟）
  └── 低优先级（即时响应）→ 内联类 ❌ 不捕获，但不需要监控
       ├── 查天气/搜索（< 5秒）
       ├── 文件读写（< 1秒）
       └── 心跳巡检（< 30秒）
```

**结论**：需要监控的任务（长时、有状态、可能崩溃）恰好全部是 spawn 类，覆盖率对核心场景接近 100%。内联盲区均为即时操作，出问题人类自己能感知，无需系统监控。

### 8.3 覆盖率提升路线

- **Phase 1（当前）**：监控 spawn 类任务，覆盖全部高优先级场景
- **Phase 2（未来）**：在 HEARTBEAT.md 和主要 Skill 中手动插入 events.jsonl 上报，补充心跳内联操作的可见性
- **Phase 3（长期）**：OpenClaw 框架层工具调用日志 hook，实现 100% 覆盖

---

## 九、未解决问题（记录）

1. **子代理 PID vs Session Key**：守护进程通过 session key 无法直接 `kill -0` 检查存活，需要子代理在启动时写 pid 文件。
2. ~~**HTML Dashboard 展示入口**~~ → ✅ 已确认：本地浏览器 + 飞书告警 + localhost:17890 API
3. **Task Parser 提炼时机**：sessions_spawn 时实时提炼（但增加调用延迟），还是心跳时批量提炼上一轮的任务？建议：sessions_spawn 后异步触发，主流程不等待。
4. **events.jsonl 归档策略**：建议每天 rotate，保留最近 7 天。
5. **localhost:17890 安全性**：仅监听 127.0.0.1，无认证。当前可接受（本机操作），未来如需远程访问需加 token。

---

## 十、重启决策策略（已确认）

**分类原则**：按任务副作用风险分级

| 任务类型 | 自动重启 | 理由 |
|---------|---------|------|
| 视频制作（article2video） | ✅ 自动（≤3次） | 纯生成，无外部副作用，断点恢复安全 |
| 数据采集（tech-updates-collector） | ✅ 自动（≤2次） | 幂等操作，重复采集无害 |
| 写作系统（tech-updates-writer） | ✅ 自动（≤2次） | 有 checkpoint，断点恢复机制完善 |
| 微信公众号发布（weixin-publisher） | ❌ 人工确认 | 可能产生重复草稿，需人工判断 |
| 视频号发布（channels-publisher） | ❌ 人工确认 | 可能重复上传，需人工判断 |
| B站发布（bili-publisher） | ❌ 人工确认 | 同上 |
| 未知任务 | ❌ 人工确认 | 默认保守 |

**自动重启触发条件**（三步缺一不可）：
1. 崩溃原因已识别（OOM / 超时 / 进程消失）
2. 资源评估通过（内存充足 + 并发数在限制内）
3. 今日重启次数 < 上限（防止无限循环）

**Dashboard 一键重启**：对需要人工确认的任务，Dashboard 提供重启按钮，人类点击后守护进程在 ≤30 秒内执行。

---

*v0.4 — 2026-04-04*
*核心更新：Dashboard 展示方案确认（本地浏览器+飞书告警+localhost API），一键操作按钮设计（restart/skip/pause），重启决策分类表（生成类自动重启，发布类人工确认），任务捕获覆盖率分析（spawn 类 ≈ 全部高优先级场景，内联盲区为即时操作无需监控）*
