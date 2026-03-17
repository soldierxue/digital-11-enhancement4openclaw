# Kiro CLI Coding Agent Skill

## 触发关键词

当用户消息中包含以下关键词时，使用 Kiro CLI 处理：
- "kiro"、"写代码"、"编程"、"开发"、"coding"
- "创建项目"、"重构"、"修复 bug"、"写测试"
- "并行创建"、"同时开发"、"新项目"、"另一个项目"
- "PDF"、"图片"等

## 任务路由

### → 发送给 Kiro CLI
- 编写任何代码（脚本、API、工具、测试）
- 创建或修改文件
- 系统配置、安装依赖
- 需要命令执行 + 验证的多步骤任务
- 代码重构、性能优化
- 项目脚手架搭建
- 处理图片和PDF文件
- 并行创建/开发多个项目

### → 由 OpenClaw 主 Agent 直接处理
- 对话式回复、信息查询
- 发送消息（Feishu、Slack、邮件）
- 简单单行命令（< 3 行，一次性）
- 非编码类任务
- 私域文章阅读比如微信公众号文章，Medium，SemiAnalysis 等专业媒体文章
- Kiro CLI 未明确定义的其他任务

## 使用方式

### 一次性查询
```
kiro-cli chat --no-interactive --trust-all-tools "your query"
```

### 交互式会话（通过 ACP）
使用 acp_client.py 中的 ACPClient 类进行会话管理。

### 带规划的复杂任务
使用 Kiro 的 /plan 模式进行多步骤功能开发。

## 多项目并发支持

KiroBridge 支持按项目名管理多个独立的 kiro-cli 进程，实现并发开发。

### 核心规则
- **同名项目 → 复用**：相同 project 名称共享同一个 kiro-cli 进程和 session 上下文
- **新项目名 → 新进程**：不同 project 名称启动全新的 kiro-cli 进程，上下文完全隔离
- **不传 project → 默认模式**：向后兼容，行为与单项目模式一致

### OpenClaw 判断逻辑

当用户提到项目相关操作时，OpenClaw 应：
1. 提取用户消息中的项目名
2. 调用 `bridge.is_same_project(name)` 判断是否已有同名项目
3. 已有 → 复用（传入相同 project 名），保持上下文连续性
4. 没有 → 创建新进程（传入新 project 名）

### 调用示例

```python
from kiro_bridge import KiroBridge

bridge = KiroBridge()

# 单项目（默认模式，向后兼容）
bridge.prompt("创建一个 Flask API")

# 指定项目名，后续同名调用共享上下文
bridge.prompt("搭建项目骨架", project="my-api")
bridge.prompt("添加数据库连接", project="my-api")  # 复用上下文

# 启动新项目（独立进程）
bridge.prompt("创建 React 前端", project="my-frontend")

# 并行创建多个项目
bridge.prompt_parallel([
    {"project": "svc-auth", "text": "创建认证微服务"},
    {"project": "svc-order", "text": "创建订单微服务"},
], max_workers=3)

# 查看所有活跃项目
bridge.list_projects()

# 停止单个项目
bridge.stop_project("my-api")

# 停止所有项目
bridge.stop()
```

### 自动上下文管理
每个项目独立跟踪上下文使用率，当某个项目的 session 上下文超过 80% 时自动轮换新 session，不影响其他项目。
