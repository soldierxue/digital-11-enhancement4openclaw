# Claw Manager — 设计文档 v0.5

> **目标**：从主会话对话中提炼人类任务，主动跟踪执行状态，无需人类询问进展。
> **定位**：OpenClaw 的任务神经系统——感知、调度、自愈、进化。
> **核心约束**：自身资源消耗必须恒定，与任务数量无关；不能成为系统瓶颈。

版本：v0.5 | 日期：2026-04-04 | 作者：Digital11

---

## 一、问题背景（过去一周真实教训）

| 故障 | 原因 | 损失 |
|------|------|------|
| 视频 Orchestrator 今日死亡4次 | Remotion 5实例并发OOM，心跳30分钟后才发现 | ~6小时 |
| 微信7篇文章全部发布失败 | IP白名单错误，子代理误报成功 | 完整重跑 |
| 写作系统 Orchestrator 死亡1小时未被发现 | 看门狗被误取消 | 1小时延误 |
| 主会话 context 膨胀 | 无工具输出截断 | compaction 频繁 |
| 文章事实错误（Gemini日期） | 写作系统无官方来源验证 | 人工修正+重发 |

根本原因：没有统一的任务感知层。任务状态散落在多个 state.json 里，主会话是唯一知道全局的地方，但主会话不是守护进程。

---

## 二、宿主机资源实测（2026-04-04）

**硬件配置**：总内存 15.7 GB | 可用 ~8 GB | Swap 2 GB | 磁盘 96 GB，已用 49 GB（51%）

| 进程 | 内存 | 说明 |
|------|------|------|
| openclaw-gateway | 1,398 MB | 主进程，常驻 |
| openclaw-tui | 502 MB | 终端 UI |
| Remotion 渲染（每实例） | 476 MB | 视频渲染 |
| Chromium | ~1,159 MB | 发布任务 |
| gnome-shell | 416 MB | 桌面 |
| LiteLLM | 306 MB | 模型代理 |

**关键发现**：今日 OOM 真实原因是 Remotion 同时跑了 5 个实例（476MB × 5 = 2,380MB），并发控制缺失才是真正原因。已修复：VIDEO-ORCHESTRATOR.md Phase 4 启动前 Remotion 实例数 ≤ 2，可用内存 > 3,000MB。

**Claw Manager 自身资源**：

| 组件 | 内存 |
|------|------|
| daemon.py（Python守护进程） | 25-40 MB（固定） |
| localhost:17890 微型 API | < 5 MB（固定） |
| HTML 生成 | 0 MB常驻（按需生成） |
| 合计上限（systemd限制） | 64 MB（守护进程自身） |

截图子进程：~400MB 瞬时，用完即还。

---

## 三、关键设计决策

### 3.1 任务信息来源：从主会话对话中提炼

人类不需要手动填表。Claw Manager 读取 sessions_spawn 上下文，用 LLM 一次性提炼结构化任务：
- 输入：子代理标签 + 任务描述 + 最近5轮对话
- 输出：`{label, skill, estimatedMinutes, stateFile, successCriteria}`

提炼动作是一次性的——只在任务登记时发生，之后用规则引擎监控，不再消耗 LLM token。

### 3.2 守护进程：事件驱动，资源恒定

核心设计：守护进程做的事情固定，与任务数量无关。

每 30 秒循环（单线程）：
1. 读取 watch.json → O(1)
2. check_system_resources() → 所有任务共享一次，O(1)
3. for task in running_tasks: check_file_mtime / check_process_alive / match_log_patterns（每项 < 5ms）
4. 有事件 → 写 events.jsonl，更新 state.json，生成 dashboard.html
5. 有告警 → 飞书推送截图
6. 无事件 → 休眠

由 systemd user service 管理：MemoryMax=64MB（自身）/ CPUWeight=50 / 截图等重型操作派生独立子进程。

### 3.3 文件作为 IPC 总线

不使用 socket、HTTP 或消息队列。

| 文件 | 写入方 | 读取方 | 用途 |
|------|--------|--------|------|
| watch.json | 主会话 Agent | 守护进程 | 任务注册/更新 |
| events.jsonl | 守护进程 + 子代理 | 守护进程 | 事件流（append-only） |
| state.json | 守护进程 | 主会话 + 心跳 | 当前快照 |
| alerts.jsonl | 守护进程 | 主会话 | 待处理告警队列 |

子代理上报只需一行：
```bash
echo '{"ts":1743750123,"source":"video-orch","event":"phase_done","phase":"3","progress":"3/7"}' >> ~/.openclaw/claw-manager/events.jsonl
```

---

## 四、HTML Dashboard 设计

### 4.1 确认方案：三层组合

| 方案 | 常驻内存 | CPU | 网络依赖 | 可靠性 | 交互 |
|------|---------|-----|---------|--------|------|
| 本地浏览器（✅选定） | 0（开时~500MB） | 0常驻 | 无 | ★★★★★ | 完整 |
| OpenClaw Canvas | 0 | 0常驻 | 依赖Gateway | ★★★★ | 受限 |
| 飞书截图 | 0 | 截图时瞬时 | 需飞书API | ★★★ | 不可交互 |

- **层 1**：本地浏览器（零依赖，内嵌30秒自动刷新）
- **层 2**：飞书告警截图（异常时用 headless Chromium 截图推送）
- **层 3**：localhost:17890 微型 API（Dashboard 按钮：🔄 重启 / ⏭️ 跳过 / ⏸️ 暂停队列）

### 4.2 Dashboard 布局

三栏布局（GitHub Dark + Linear 质感，`#0d1117` 背景，30秒自动刷新）：
- **左栏**：资源监控（CPU/内存/磁盘进度条 + 今日峰值 + 磁盘I/O）
- **中栏**：任务看板（今日统计 + 各任务卡片，含队员标签、依赖关系、运行时长、成本展示）
- **右栏**：告警与事件流（daemon_error 去重抑制5分钟 + 合并显示×N + 降权颜色）
- **底部**：全宽甘特图（统一 t_min/t_max，5个均匀刻度，to_pct() 辅助对齐）

---

## 五、自动重启决策

### 分类策略

| 任务类型 | 自动重启 | 理由 |
|----------|---------|------|
| 视频制作（article2video） | ✅ 自动（今日≤3次） | 纯生成，断点恢复安全 |
| 数据采集（tech-updates-collector） | ✅ 自动（≤2次） | 幂等，重复无害 |
| 写作系统（tech-updates-writer） | ✅ 自动（≤2次） | checkpoint 完善 |
| 微信公众号发布 | ❌ 人工确认 | 可能产生重复草稿 |
| 视频号/B站发布 | ❌ 人工确认 | 可能重复上传 |
| 未知任务 | ❌ 人工确认 | 默认保守 |

### 重启决策表

| 崩溃原因 | 资源充足 | 决策 | 动作 |
|---------|---------|------|------|
| OOM（已知） | 是 | 自动重启 | 先释放系统缓存再重启 |
| OOM（已知） | 否 | 排队等待 | 入队 + 通知用户 |
| OOM 疑似 | 是 | 自动重启（1次） | 超过1次则通知用户 |
| 已知错误 + 已知修复 | 任意 | 应用修复后重启 | IP白名单错误→停止通知人类 |
| 重启次数 ≥ 3 | 任意 | 停止，通知人类 | 附带信号供诊断 |
| 超时卡住 | 是 | 自动重启（断点恢复） | 从上次检查点继续 |
| 原因未知 | 任意 | 停止，通知人类 | 默认保守 |

---

## 六、系统架构

```
用户请求 → OpenClaw 主会话
                ↓ spawn
        各 Skill 子代理 (Scout/Quill/Frame/Echo/Forge)
                ↓ 写入
        events.jsonl ← daemon 读取
                ↓ 30s 轮询
        Claw Manager Daemon (Warden)
                ↓ 生成
        dashboard.html ← HTTP server ← 浏览器访问
                ↓ 告警
        飞书消息
```

---

## 七、任务画像（实测数据）

| Skill | 峰值内存 | 平均时长 | 并发上限 | 特殊约束 |
|-------|---------|---------|---------|---------|
| article2video | 2,400 MB | 38 min/篇 | Remotion ≤2实例 | 渲染前检查内存+实例数 |
| weixin-publisher | 600 MB | 8 min/篇 | 1 | 发布前验证 access_token |
| channels-publisher | 600 MB | 15 min | 1 | 网络错误300333需重试 |
| writing-system | 400 MB | 220 min | 1 | 运行时不启动其他重型任务 |
| tech-updates-collector | 200 MB | 15 min | 1 | 幂等 |

---

## 八、资源目标与告警阈值

| 资源 | 健康区间 | 告警 | 紧急 | 动作 |
|------|---------|------|------|------|
| CPU | 50-70% | >80% | >90% | 暂停低优先级任务 |
| 内存 | 50-70% | >75% | >85% | 拒绝新任务入队，通知用户 |
| 磁盘 | <65% | >70% | >80% | 清理临时文件，通知扩容 |
| Remotion 实例数 | ≤2 | =3 | ≥4 | 排队等待，不强制启动 |

---

## 九、实现路线图

**Phase 0（已完成）**：
- ✅ VIDEO-ORCHESTRATOR.md 约束3：Remotion 实例数 + 内存硬性检查

**Phase 1（已完成）**：
- ✅ daemon.py：轮询 + 规则引擎 + 基础重启决策 + localhost:17890 API
- ✅ daemon_error 5分钟去重抑制（写入侧）+ 展示合并×N + 降权颜色
- ✅ dict.__format__ bug 修复（3处 isinstance 保护）
- ✅ task_profiles.json：任务画像（基于实测）
- ✅ systemd user service（MemoryMax=64MB, CPUWeight=50）
- ✅ HTML Dashboard v2：GitHub Dark + Linear 质感，三栏布局，甘特时间线

**Phase 2（计划中）**：
- sessions_spawn 后异步触发任务提炼
- 任务队列 + 等待条件评估
- Dashboard 增加甘特依赖箭头

**Phase 3（持续）**：
- 故障模式自动匹配和积累
- 任务画像自动更新（每次完成后记录实测数据）
- 优化建议生成

---

## 十、任务捕获覆盖率分析

### 10.1 各任务入口的可见性

| 触发方式 | 可捕获 | 原因 |
|---------|--------|------|
| sessions_spawn 子代理 | ✅ 完整 | 有明确的 spawn 事件可 hook |
| Cron Job | ✅ 完整 | Cron 最终也通过 spawn 启动 |
| Swarm（多子代理协作） | ✅ 完整 | 每个 swarm 成员都是一次 spawn |
| Heartbeat 触发的子代理 | ✅ 完整 | 心跳内的 sessions_spawn 同样可 hook |
| Heartbeat 内联操作 | ❌ 盲区 | 直接 exec/读文件，没有 spawn 边界 |
| Skill 内联执行 | ❌ 盲区 | Skill 在主会话内运行，工具调用无独立进程 |
| 用户即时请求（查天气等） | ❌ 盲区 | 主会话直接响应，< 5秒，无需监控 |

高优先级（长时运行）→ 几乎都是 spawn 类 ✅ 可捕获：视频制作（40-90分钟）/ 写作系统（2-3小时）/ 公众号发布（10-30分钟）

---

## 十一、队员角色系统（SKILL_PROFILES）

| 队员 | Emoji | 角色 | 对应 Skill |
|------|-------|------|----------|
| Scout | 🔍 | 情报官 | tech-updates-collector |
| Quill | ✍️ | 主笔 | tech-updates-writer |
| Frame | 🎬 | 导演 | article2video |
| Echo | 📢 | 运营 | channels-publisher / weixin-publisher |
| Forge | 🔧 | 工程师 | kiro-cli |
| Warden | 🛡️ | 守卫 | claw-manager（常驻） |

---

## 十二、成本追踪

事件上报时附带 cost 字段，daemon.py 自动累加到 watch.json：

```json
{"ts":1775287573, "event":"phase_done", "source":"tech-writer-orchestrator-0404", "cost_tokens_in":45000, "cost_tokens_out":12000, "model":"claude-sonnet-4-6"}
```

模型定价：claude-sonnet-4-6（$15/M tokens）、claude-opus-4-6（$75/M）、claude-haiku-3-5（$4/M）

---

## 十三、待解决问题

1. **子代理 PID vs Session Key**：守护进程无法直接 `kill -0` 检查存活，需子代理启动时写 pid 文件
2. **Task Parser 时机**：sessions_spawn 后异步提炼（推荐），不阻塞主流程
3. **events.jsonl 归档**：每天 rotate，保留最近 7 天
4. **localhost:17890 安全**：仅 127.0.0.1，无认证，当前可接受；远程访问需加 token
5. **成本追踪完整闭环**：需要 Orchestrator 埋点 cost 字段（task_parser.py 已更新，daemon.py 侧未完成）

---

v0.5 — 2026-04-04 | 作者：Digital11

核心更新：Dashboard v2 完成（GitHub Dark，三栏布局，甘特时间线对齐修复，右栏事件流去噪），daemon.py bug 修复（dict.__format__ + daemon_error 去重），API server 完成，任务捕获覆盖率分析，队员角色系统确认。
