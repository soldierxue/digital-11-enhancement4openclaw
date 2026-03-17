# Kiro CLI Coding Agent Skill

## 触发关键词

当用户消息中包含以下关键词时，使用 Kiro CLI 处理：
- "kiro"、"写代码"、"编程"、"开发"、"coding"
- "创建项目"、"重构"、"修复 bug"、"写测试"
- “PDF”、“图片”等

## 任务路由

### → 发送给 Kiro CLI
- 编写任何代码（脚本、API、工具、测试）
- 创建或修改文件
- 系统配置、安装依赖
- 需要命令执行 + 验证的多步骤任务
- 代码重构、性能优化
- 项目脚手架搭建
- 处理图片和PDF文件

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
