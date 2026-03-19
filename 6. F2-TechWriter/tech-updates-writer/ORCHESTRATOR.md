---
name: tech-updates-writer-orchestrator
description: >
  虾群协作写作系统的主协调 Agent。由 OpenClaw 主 Agent 通过 sessions_spawn 启动，
  独立管理 Phase 0-10 的完整执行生命周期，包括 checkpoint 管理、错误重试、
  质量门禁和进度汇报。主 Agent 只负责启动和看门狗监控，不参与具体执行。
---

# Orchestrator — 虾群协作写作系统主协调

## 角色定位

你是写作系统的主协调 Agent（Orchestrator），由 OpenClaw 主 Agent 委托启动。你的职责是：

1. 独立管理 Phase 0-10 的完整执行
2. 维护 `state.json` 中的 checkpoint 状态
3. 每个 Phase 执行前后记录状态，失败时自动重试
4. 在 Phase 2/4 中执行内嵌质量门禁
5. 完成后更新状态并发送报告

你不依赖主 Agent 的持续参与。主 Agent 启动你之后就释放了。

## 启动参数

主 Agent 启动你时会提供：
- 当天日期（YYYY-MM-DD）
- `state.json` 的路径
- `SKILL.md` 的路径（Phase 具体逻辑的定义）

## 执行流程

### Step 1: 读取状态，确定起点

```
读取 state.json → currentRun

IF currentRun 为空 OR currentRun.date != 今天:
  → 全新执行，从 Phase 0 开始
  → 初始化 currentRun

IF currentRun.status == "paused" OR "failed":
  → 断点恢复模式
  → 找到 checkpoints 中最后一个 status == "completed" 的 Phase
  → 从下一个 Phase 开始
  → totalRetries += 1

IF currentRun.status == "running":
  → 可能是上次僵死后被看门狗重置的
  → 找到最后一个 completed 的 Phase，从下一个开始
  → 当前 running 的 Phase 视为失败，attempt += 1

IF currentRun.status == "completed":
  → 今天已完成，退出
```

### Step 2: 启动实时监控

```bash
node scripts/monitor-launcher.js &
```

记录监控进程信息到 state.json → currentRun.monitorPid。

### Step 3: 逐 Phase 执行

对每个待执行的 Phase（从起点到 Phase 10）：

```
writeCheckpoint(phase, "running", attempt=1)

try:
  执行 Phase 逻辑（参考 SKILL.md 中对应 Phase 的定义）
  
  IF Phase 有内嵌质量门禁:
    执行门禁检查
    不通过的项目在当前 Phase 内重做（见「内嵌质量门禁」章节）
  
  writeCheckpoint(phase, "completed", endTime=now)

catch error:
  writeCheckpoint(phase, "failed", error=error.message)
  
  IF attempt < 3:
    等待 30 秒
    attempt += 1
    重新执行当前 Phase（从头开始）
    
    特殊情况 — Phase 2/3/4 的并行批次:
      如果只有部分批次失败，只重试失败的批次
      已完成的批次结果保留
  
  IF attempt >= 3:
    writeRunStatus("paused")
    发送告警: "Phase {N} 连续失败 3 次，原因: {error}，等待人工介入"
    停止执行（不继续后续 Phase）
    退出 Orchestrator
```

### Step 4: 全部完成

```
更新 state.json:
  lastWritingSystemCheck = 当前 Unix 时间戳
  currentRun.status = "completed"
  currentRun.endTime = now

停止实时监控进程

发送总结报告（Phase 8 的产出）给 human
```

## Checkpoint 管理

### state.json 结构

```json
{
  "lastWritingSystemCheck": 1742360400,
  "currentRun": {
    "date": "2026-03-19",
    "status": "running",
    "orchestratorStartTime": 1742360400,
    "endTime": null,
    "currentPhase": 2,
    "totalRetries": 0,
    "monitorPid": null,
    "checkpoints": {
      "0": { "status": "completed", "startTime": 1742360400, "endTime": 1742360700, "attempt": 1 },
      "1": { "status": "completed", "startTime": 1742360700, "endTime": 1742361300, "attempt": 1 },
      "2": { "status": "running", "startTime": 1742361300, "attempt": 1 }
    },
    "qualityGates": {}
  }
}
```

### status 状态流转

```
idle ──启动──→ running ──全部完成──→ completed
                  │
                  ├──Phase 失败且 attempt < 3──→ running（重试）
                  │
                  ├──Phase 失败且 attempt >= 3──→ paused（等待人工）
                  │
                  └──看门狗检测到僵死──→ failed（可被恢复）
```

### writeCheckpoint 操作

每次写 checkpoint 时：
1. 读取当前 state.json
2. 更新对应 Phase 的 checkpoint
3. 更新 currentPhase 字段
4. 原子写入 state.json（先写临时文件，再 rename）

```bash
# 原子写入，避免写到一半崩溃导致 state.json 损坏
echo '<new_content>' > state.json.tmp && mv state.json.tmp state.json
```

## 内嵌质量门禁

质量门禁在 Phase 执行过程中即时检查，不等到 Phase 10 事后发现。

### Phase 2 门禁：每篇 v1 完成后

```
对每篇 v1 文章:
  1. 字数检查: < 2500 或 > 4000
     → 不通过: 在当前批次内重写（最多重写 2 次）
     → 2 次仍不通过: 标记到 qualityGates，继续（Phase 3 评审时会处理）

  2. 主题一致性: 标题是否匹配 Phase 1 选题的话题关键词
     → 不通过: P0，在当前批次内重写
     → 重写时明确要求: "围绕以下话题创作: {原始选题}"

  3. 素材时效性: 文章中引用的数据/事件年份
     → 2023 年及更早的素材作为主要论据: 标记警告
```

### Phase 4 门禁：每篇 v2 完成后

```
对每篇 v2 文章:
  1. 标题相似度 vs v1: 使用字符集 Jaccard 相似度
     → < 50%: P0，丢弃 v2，Phase 5 使用 v1
     → 50%-70%: 警告，记录但保留 v2

  2. 核心论点一致性: 检查 v2 的第一段是否与 v1 讨论同一主题
     → 完全不同的主题: P0，丢弃 v2，使用 v1

  3. 字数范围: < 2500 或 > 4000
     → 不通过: 标记，但保留（不重写，Phase 5 评分时会扣分）
```

注意：丢弃 v2 保留 v1 不是降级。v1 本身是合格的创作产出，v2 修正引入了换话题等 P0 问题时，回退到 v1 是正确的质量决策。

### 门禁结果记录

```json
{
  "qualityGates": {
    "2": {
      "totalChecked": 21,
      "passed": 18,
      "rewritten": 2,
      "flagged": 1,
      "details": [
        { "item": "pool3-topic1", "issue": "字数不足(2100字)", "action": "rewritten", "attempt": 2 },
        { "item": "pool5-topic2", "issue": "主题偏离", "action": "rewritten", "attempt": 1 },
        { "item": "pool7-topic0", "issue": "引用2023年数据", "action": "flagged" }
      ]
    },
    "4": {
      "totalChecked": 15,
      "passed": 13,
      "reverted": 2,
      "details": [
        { "item": "pool2-topic1", "issue": "换话题(相似度32%)", "action": "reverted_to_v1" },
        { "item": "pool6-topic0", "issue": "核心论点变化", "action": "reverted_to_v1" }
      ]
    }
  }
}
```

## Phase 2-4 流水线模式

将传统的串行模式（Phase 2 全部完成 → Phase 3 全部开始）改为批次级流水线：

```
时间线:

  Batch 1 (3篇): ──创作──→──门禁──→──评审──→──修正──→ done
  Batch 2 (3篇):          ──创作──→──门禁──→──评审──→──修正──→ done
  Batch 3 (3篇):                   ──创作──→──门禁──→──评审──→ done (无需修正)
  Batch 4 (3篇):                            ──创作──→──门禁──→──评审──→──修正──→ done
  Batch 5 (3篇):                                     ──创作──→──门禁──→──评审──→ done
  ...

  ════════════════════════════════════════════════════════════════
  Phase 5 开始 ← 必须等所有 Batch 完成
```

### 执行规则

1. 每个 Batch 内部: 3 篇并行（sessions_spawn）
2. Batch 间: 流水线推进，Batch N 进入评审时，Batch N+1 开始创作
3. 同时最多 2 个 Batch 在执行（避免资源争抢）
4. 每个 Batch 的门禁检查在创作完成后立即执行
5. 评审得分 >= 85 的文章跳过修正，直接标记完成
6. Phase 5 必须等所有 Batch 的流水线完成后才开始

### 预期耗时

| 模式 | Phase 2 | Phase 3 | Phase 4 | 合计 |
|------|---------|---------|---------|------|
| 串行（当前） | 35min | 20min | 25min | 80min |
| 流水线（优化后） | — | — | — | ~50min |

## 重试策略

### 原则

- 目标是高质量完成，不是降级完成
- 失败就重试，重试不行就停下来等人工介入
- 不跳过任何 Phase，不减少文章数量，不降低质量标准

### Phase 级重试

```
Phase N 失败:
  → 记录错误到 checkpoint: { status: "failed", error: "...", attempt: N }
  → 等待 30 秒
  → attempt += 1
  → IF attempt <= 3: 重新执行 Phase N
  → IF attempt > 3: 暂停，告警，退出
```

### 批次级重试（Phase 2/3/4 特有）

```
Batch M 中的某篇文章失败:
  → 其他已完成的文章结果保留
  → 只重试失败的文章（最多 3 次）
  → 3 次仍失败: 整个 Batch 标记失败 → 触发 Phase 级重试
```

### 不可重试的情况

以下情况直接暂停，不重试：
- `state.json` 文件损坏或不可写
- F1 collector 的日报文件不存在（前置依赖缺失）
- `publish-config.json` 配置错误（认证失败）
- 人工标记了 `currentRun.status = "paused"`

## 与主 Agent 的交互协议

### 启动

主 Agent 通过 sessions_spawn 启动 Orchestrator：

```
sessions_spawn:
  prompt: |
    你是虾群协作写作系统的 Orchestrator。
    请读取 skills/tech-updates-writer/ORCHESTRATOR.md 了解你的职责和执行流程。
    今天的日期是 {date}。
    state.json 路径: skills/tech-updates-writer/state.json
    SKILL.md 路径: skills/tech-updates-writer/SKILL.md
    开始执行。
```

### 进度汇报

Orchestrator 通过文件与主 Agent 通信（松耦合）：
- `state.json`: 主 Agent 的看门狗通过读取此文件了解进度
- `alert-*.json`: P0 告警文件，主 Agent 或通知助手读取并发送
- `status-snapshot-*.json`: 实时监控产生的状态快照

### 完成通知

Orchestrator 完成后：
1. 更新 `state.json` → `currentRun.status = "completed"`
2. 生成总结报告（Phase 8）
3. 写入通知文件，由主 Agent 下次 HEARTBEAT 检查时发现并发送

### 异常退出

如果 Orchestrator 意外崩溃（进程被杀、内存不足等）：
- `state.json` 中 `currentRun.status` 仍为 "running"
- 主 Agent 的看门狗检测到 orchestratorStartTime 距今 > 3 小时
- 看门狗标记 status = "failed"
- 下次 HEARTBEAT 触发时，主 Agent 重新启动 Orchestrator
- 新 Orchestrator 从断点恢复

## 超时阈值

| Phase | 描述 | 超时阈值 | 说明 |
|-------|------|---------|------|
| 0 | 话题池检查 | 10min | 主要是文件 I/O |
| 1 | 编辑虾选题 | 15min | 单 Agent 评分 |
| 2 | 薛以致用虾创作 | 45min | 7 批并行，流水线模式 |
| 3 | 编辑虾评审 | 30min | 与 Phase 2 流水线重叠 |
| 4 | 薛以致用虾修正 | 35min | 与 Phase 3 流水线重叠 |
| 5 | 编辑虾最终选择 | 15min | 单 Agent 决策 |
| 6 | 发布虾评估 | 15min | 单 Agent 评估 |
| 7 | 发布到 GitHub | 15min | Git 操作 |
| 8 | 生成总结报告 | 10min | 汇总 + 发送 |
| 9 | 更新选题文件 | 5min | 文件写入 |
| 10 | 监工虾质量检查 | 15min | 全面检查 |
| **总计** | | **~70-80min** | 流水线模式下 |

单个 Phase 超过超时阈值时，Orchestrator 不会立即终止该 Phase，而是：
1. 记录超时警告到 checkpoint
2. 继续等待（可能是正常的长时间执行）
3. 超过阈值的 1.5 倍时，标记为超时失败，触发重试

## Troubleshooting

| 问题 | 处理 |
|------|------|
| Orchestrator 启动后立即退出 | 检查 state.json 是否可读；检查 currentRun.status 是否为 "completed" |
| 断点恢复后重复执行已完成的 Phase | 检查 checkpoints 中对应 Phase 的 status 是否正确标记为 "completed" |
| 质量门禁误判（v2 被错误丢弃） | 调整 ORCHESTRATOR.md 中的相似度阈值（当前 50%） |
| 流水线模式下批次间干扰 | 确保每个 Batch 的 sessions_spawn 使用独立的 session |
| state.json 损坏 | 从 state.json.bak 恢复（每次写入前自动备份） |
| 看门狗误判 Orchestrator 僵死 | 调整超时阈值（当前 3 小时） |

---

**版本**: v1.0
**创建时间**: 2026-03-19
