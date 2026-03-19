# 实时监控虾使用指南

**更新时间**: 2026-03-05 04:25 UTC  
**功能**: 写作系统执行期间每10分钟自动检查进度并主动告知状态

---

## 🎯 功能概述

### 实时监控 vs 事后检查

| 功能 | 实时监控虾 | 监工虾（事后） |
|------|----------|--------------|
| **时机** | 执行期间，每10分钟 | 执行完成后 |
| **目的** | 实时进度追踪 + 早期问题发现 | 全面质量检查 |
| **输出** | 状态快照 + 即时告警 | 完整质量报告 |
| **用途** | 让你随时知道进度 | 详细分析和改进 |

**两者配合使用**：
- 实时监控虾：执行期间持续监控（类似GPS导航）
- 监工虾：执行结束后全面检查（类似到达后验货）

---

## 🚀 使用方法

### 方法1: 手动启动（测试/调试）

```bash
# 启动实时监控（前台运行）
cd /home/ubuntu/clawd
node memory/writing/scripts/realtime-supervisor.js

# 或指定日期
node memory/writing/scripts/realtime-supervisor.js 2026-03-05
```

**预期输出**：
```
🔍 实时监控虾启动
日期: 2026-03-05
检查间隔: 10分钟

==================================================
📝 检查 Phase 1: 编辑虾选题...
...
==================================================

📊 写作系统实时状态

检查时间: 2026-03-05 15:00:00
已运行: 0分钟
当前阶段: Phase 1
进度: 0%
预计剩余: 约110分钟

✅ 已完成阶段
暂无

✅ 暂无问题

---
下次检查: 10分钟后
```

### 方法2: 后台启动（生产环境）

```bash
# 使用启动器（推荐）
node memory/writing/scripts/monitor-launcher.js &

# 查看进程
ps aux | grep realtime-supervisor

# 停止监控
pkill -f realtime-supervisor
```

### 方法3: 集成到HEARTBEAT（自动）

已集成到HEARTBEAT.md，写作系统执行时自动启动：

```markdown
## 虾群协作写作系统 📝

**实时监控**: 在开始执行前，启动实时监控虾
- 命令：`node memory/writing/scripts/monitor-launcher.js &`
- 功能：每10分钟检查进度并主动告知状态
- 输出：实时状态报告 + P0问题告警
```

---

## 📊 状态报告格式

### 每10分钟的状态快照

```markdown
## 📊 写作系统实时状态

**检查时间**: 2026-03-05 15:30:00
**已运行**: 30分钟
**当前阶段**: Phase 3
**进度**: 37%
**预计剩余**: 约60分钟

### ✅ 已完成阶段
- Phase 0
- Phase 1
- Phase 2

### ✅ 暂无问题

---
*下次检查: 10分钟后*
```

### 发现问题时的告警

```markdown
## 📊 写作系统实时状态

**检查时间**: 2026-03-05 16:00:00
**已运行**: 60分钟
**当前阶段**: Phase 4
**进度**: 50%
**预计剩余**: 约50分钟

### ✅ 已完成阶段
- Phase 0
- Phase 1
- Phase 2
- Phase 3

### ⚠️ 发现的问题
1. **[P0]** Phase 4: 发现5篇疑似换话题

---
*下次检查: 10分钟后*
```

---

## 🔍 检测内容

### Phase检测

自动检测当前执行到哪个Phase：

- **Phase 0**: 检查话题池文件是否存在
- **Phase 1**: 检查选题文件是否存在
- **Phase 2**: 检查v1文章数量（需≥21篇）
- **Phase 3**: 检查评审文件是否存在
- **Phase 4**: 检查v2文章数量
- **Phase 5**: 检查最终选择文件是否存在
- **Phase 6**: 检查发布决策文件是否存在
- **Phase 7**: 检查GitHub发布文件（需≥3篇）

### 快速质量检查

在检测到相应Phase完成后，立即进行质量检查：

#### Phase 4完成后
- ✅ 检测是否有换话题（对比v1/v2标题相似度）
- ✅ 统计换话题数量
- ✅ 如果发现换话题，立即P0告警

#### Phase 5完成后
- ✅ 检测2024年素材是否给了满分
- ✅ 检查时效性评分是否正确
- ✅ 如果发现评分错误，立即P0告警

---

## 📂 输出文件

### 状态快照文件

位置: `memory/writing/status-snapshot-YYYY-MM-DD-{timestamp}.json`

内容:
```json
{
  "timestamp": "2026-03-05T07:30:00.000Z",
  "elapsed": "30分钟",
  "currentPhase": "Phase 3",
  "completedPhases": ["Phase 0", "Phase 1", "Phase 2"],
  "progress": "37%",
  "issues": [],
  "estimatedCompletion": "约60分钟"
}
```

### 告警文件

位置: `memory/writing/alert-YYYY-MM-DD-{timestamp}.json`

内容:
```json
{
  "timestamp": "2026-03-05T08:00:00.000Z",
  "issues": [
    {
      "severity": "P0",
      "phase": "Phase 4",
      "message": "发现5篇疑似换话题"
    }
  ],
  "message": "完整的Markdown告警内容"
}
```

### 最终报告

位置: `memory/writing/realtime-report-YYYY-MM-DD.json`

内容:
```json
{
  "date": "2026-03-05",
  "startTime": "2026-03-05T07:00:00.000Z",
  "endTime": "2026-03-05T08:50:00.000Z",
  "duration": 110,
  "statusHistory": [...],
  "summary": {
    "totalChecks": 11,
    "p0Issues": 5,
    "p1Issues": 0
  }
}
```

---

## 🔔 通知机制

### 自动通知（已集成）

监控脚本会生成通知文件，Clawdbot定期检查并发送：

1. **状态更新**（每10分钟）:
   - 生成: `status-update-{timestamp}.txt`
   - 发送: 通过Feishu告知进度

2. **P0告警**（立即）:
   - 生成: `notify-{timestamp}.txt`
   - 发送: 立即通过Feishu告警

### 通知助手

Clawdbot需要定期运行通知助手：

```bash
node memory/writing/scripts/notification-helper.js
```

建议频率：每1-2分钟检查一次

---

## ⏱️ 时间估算

### Phase预计耗时

| Phase | 预计时间 | 说明 |
|-------|---------|------|
| Phase 0 | 5分钟 | 话题池检查 |
| Phase 1 | 10分钟 | 选题 |
| Phase 2 | 35分钟 | 创作21篇（并行） |
| Phase 3 | 20分钟 | 评审21篇（并行） |
| Phase 4 | 25分钟 | 修正（并行） |
| Phase 5 | 15分钟 | 最终选择 |
| Phase 6 | 10分钟 | 发布评估 |
| Phase 7 | 10分钟 | GitHub发布 |
| **总计** | **约110分钟** | 1小时50分钟 |

### 进度计算

```
进度 = 已完成Phase数 / 总Phase数
预计剩余 = Σ(未完成Phase的预计时间)
```

---

## 🧪 测试示例

### 模拟测试（无需真实写作系统）

```bash
# 创建测试文件夹
mkdir -p /tmp/test-monitor/selected-topics
echo "test" > /tmp/test-monitor/selected-topics/2026-03-05-selection.md

# 启动监控（会检测到Phase 1完成）
cd /home/ubuntu/clawd
node memory/writing/scripts/realtime-supervisor.js 2026-03-05

# 模拟Phase 2完成
mkdir -p /tmp/test-monitor/drafts
for i in {0..2}; do
  for j in {0..6}; do
    echo "# Test Article" > /tmp/test-monitor/drafts/2026-03-05-pool${i}-topic${j}-v1.md
  done
done

# 等待下次检查（10分钟），或手动触发
```

### 实战测试

在今天（2026-03-05）15:00写作系统执行时：

1. ✅ 自动启动实时监控
2. ✅ 每10分钟收到状态更新
3. ✅ 发现问题立即告警
4. ✅ 执行完成生成最终报告

---

## 💡 最佳实践

### 1. 监控期间

- ✅ 每次收到状态更新，确认进度正常
- ✅ 如果进度停滞超过20分钟，检查是否卡住
- ✅ 收到P0告警立即查看

### 2. 问题处理

**Phase 4换话题告警**：
```bash
# 1. 立即查看告警详情
cat memory/writing/alert-*.json

# 2. 检查是否确实换话题
ls memory/writing/drafts/*-v2.md

# 3. 如果确认换话题，停止执行并修复
pkill -f realtime-supervisor
```

**Phase 5时效性评分告警**：
```bash
# 1. 查看最终选择文件
cat memory/writing/final-selection-*.md

# 2. 确认2024素材是否给满分

# 3. 如果确认错误，考虑重新执行Phase 5
```

### 3. 完成后

```bash
# 查看最终报告
cat memory/writing/realtime-report-2026-03-05.json

# 对比事后检查报告
cat memory/writing/supervisor-report-2026-03-05.md
```

---

## 🔧 配置选项

### 修改检查间隔

编辑 `realtime-supervisor.js`:

```javascript
this.checkInterval = 5 * 60 * 1000; // 改为5分钟
```

### 修改相似度阈值

编辑 `realtime-supervisor.js`:

```javascript
if (this.calculateSimilarity(v1Title, v2Title) < 0.3) {
  // 改为30%更严格
```

### 禁用某些检查

编辑 `quickQualityCheck()` 方法，注释掉不需要的检查。

---

## 📞 问题排查

### Q: 监控启动后没有输出？
A: 检查日期是否正确，确认写作系统已开始执行。

### Q: 状态一直显示"Not started"？
A: 确认Phase 0的话题池文件已生成。

### Q: 没有收到Feishu通知？
A: 检查通知助手是否在运行：
```bash
node memory/writing/scripts/notification-helper.js
```

### Q: 监控进程意外退出？
A: 查看错误日志，可能是权限问题或文件路径错误。

---

## 📝 总结

实时监控虾提供：
- ✅ **实时进度追踪**：每10分钟知道到哪一步了
- ✅ **早期问题发现**：Phase 4/5完成立即检查
- ✅ **主动告警**：P0问题立即通知
- ✅ **时间估算**：预计还需要多久完成

**核心价值**：让你不必一直盯着，但随时知道状态。

**推荐用法**：
1. 写作系统开始执行时自动启动
2. 每10分钟主动发送状态到Feishu
3. 发现P0问题立即告警
4. 执行完成后对比事后检查报告

---

**版本**: v1.0  
**更新时间**: 2026-03-05  
**作者**: TechMolty 🦞
