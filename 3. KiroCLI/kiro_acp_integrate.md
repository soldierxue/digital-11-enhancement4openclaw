# 通过 ACP 协议将 Kiro CLI 集成为 OpenClaw 的 Peer Agent

> 本文档供 AI Agent（如 OpenClaw）读取并在本机自动执行，完成 Kiro CLI 作为 ACP Peer Agent 的完整配置与集成。
>
> 参考: [Integrate Kiro CLI into Your AI Agent via ACP](https://dev.to/aws-builders/integrate-kiro-cli-into-your-ai-agent-via-acp-10jn) | [Kiro ACP 官方文档](https://kiro.dev/docs/cli/acp/)

## 背景与价值

### 为什么需要 ACP 集成？

OpenClaw 使用 Claude API 处理所有任务，包括编码。编码任务的迭代循环（生成 → 执行 → 读取错误 → 修复 → 重复）每一步都是一次 Claude API 调用，Token 成本快速累积。

通过 ACP（Agent Communication Protocol）将编码任务路由到 Kiro CLI：

- Kiro 使用独立的 Kiro Credits 计费，不消耗 Claude API Token
- Kiro 自主完成代码生成 → 文件写入 → 测试执行 → 错误修复的完整循环
- OpenClaw（Claude API）仅负责意图识别和结果摘要，每次编码任务仅消耗 ~600–2,000 Token
- 比OpenClaw 直接 Claude API Token 使用量降低 60–80%

### ACP vs 其他方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| 直接 Claude API | 简单，无依赖 | 昂贵；每次迭代 = 新 API 调用 |
| subprocess `--no-interactive` | 易实现 | 无会话状态，输出解析脆弱 |
| ACP JSON-RPC（本方案） | 双向通信，会话管理，实时用量 | 需实现 JSON-RPC 客户端 |
| MCP 协议 | 标准化工具调用 | 单向，不适合 Kiro 作为执行者 |

> 核心区别：MCP 让 Kiro 成为你的 Agent 控制的工具；ACP 让 Kiro 成为对等的 Peer Agent。

### 架构概览

```
┌──────────────────────────────────────────────────────────┐
│              用户 (Feishu / Signal / Telegram)             │
└─────────────────────────┬────────────────────────────────┘
                          │ message
                          ▼
┌──────────────────────────────────────────────────────────┐
│              主 Agent (OpenClaw / Claude API)              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ 意图识别     │  │ 记忆管理     │  │ 任务路由       │  │
│  │ (Claude API) │  │  MEMORY.md   │  │  SKILL.md      │  │
│  └──────────────┘  └──────────────┘  └───────┬────────┘  │
└─────────────────────────────────────────────┼────────────┘
                                              │ ACP JSON-RPC 2.0
                        ┌─────────────────────▼────────────┐
                        │         acp_client.py             │
                        │  initialize / session/new         │
                        │  session/prompt                   │
                        │  session/request_permission       │
                        │  _kiro.dev/metadata (用量推送)    │
                        └─────────────────────┬────────────┘
                                              │ stdio (subprocess)
                        ┌─────────────────────▼────────────┐
                        │      kiro-cli (acp 模式)          │
                        │  ┌───────────┐  ┌─────────────┐  │
                        │  │ 代码生成  │  │ 工具执行    │  │
                        │  │ (Kiro AI) │  │ fs/terminal │  │
                        │  └───────────┘  └─────────────┘  │
                        └──────────────────────────────────┘
```

## 前置条件

1. Kiro CLI 已安装并登录（参见同目录 `kiro_install_config.md`）
2. Python 3.10+ 已安装（`python3 --version`）
3. OpenClaw 已安装并可正常运行
4. 工作目录默认为 `~/kiro-projects/`，在其下按项目名分目录存储

## 执行流程

---

## Part 1: 验证 Kiro CLI ACP 模式

### Step 1: 确认 Kiro CLI 版本与 ACP 支持

```bash
kiro-cli version
```

期望版本 ≥ 1.20.0。ACP 模式从此版本开始稳定支持。

### Step 2: 测试 ACP 握手

发送一个 `initialize` 请求验证 ACP 模式是否正常工作：

```bash
echo '{
  "jsonrpc":"2.0","id":1,"method":"initialize",
  "params":{
    "protocolVersion":1,
    "clientCapabilities":{},
    "clientInfo":{"name":"test","version":"0.1"}
  }
}' | kiro-cli acp
```

期望返回包含 `agentCapabilities` 和 `agentInfo` 的 JSON 响应。如果返回错误，检查 Kiro CLI 登录状态：

```bash
kiro-cli auth status
```

---

## Part 2: 部署 ACP 客户端

### Step 3: 创建技能目录结构

```bash
SKILL_DIR="$HOME/.openclaw/workspace/skills/kiro-cli"
mkdir -p "$SKILL_DIR"
echo "✔ 技能目录已创建: $SKILL_DIR"
```

推荐目录布局：

```
~/.openclaw/workspace/skills/kiro-cli/
├── acp_client.py       # 核心 ACP 客户端（纯 stdlib，零依赖）
├── kiro_bridge.py      # 生产级封装（会话管理 + 用量追踪）
├── usage_tracker.py    # 双轨计费追踪：Kiro Credits + Claude Token
├── test_acp.py         # 端到端集成测试
└── SKILL.md            # OpenClaw 任务路由规则
```

### 文件关联与依赖关系

```
                    ┌─────────────────┐
                    │    SKILL.md     │  ← OpenClaw 读取，决定是否将任务路由给 Kiro
                    │  (路由规则，独立) │
                    └─────────────────┘

                    ┌─────────────────┐
                    │  acp_client.py  │  ← 最底层，零外部依赖（纯 Python stdlib）
                    │  ACPClient 类   │     管理 kiro-cli 子进程 + JSON-RPC 通信
                    └────────┬────────┘
                             │ import
                    ┌────────▼────────┐
                    │ kiro_bridge.py  │  ← 依赖 acp_client.py
                    │  KiroBridge 类  │     封装会话管理、懒启动、上下文自动切换
                    └────────┬────────┘
                             │ 可选集成
                    ┌────────▼────────┐
                    │usage_tracker.py │  ← 独立模块，无 import 依赖
                    │  record_task()  │     由 KiroBridge 调用方在外部串联
                    └─────────────────┘

                    ┌─────────────────┐
                    │  test_acp.py    │  ← 依赖 acp_client.py
                    │  (集成测试)      │     直接实例化 ACPClient 验证 ACP 流程
                    └─────────────────┘
```

依赖链总结：

- `acp_client.py` 是核心基础层，仅使用 Python 标准库（json、subprocess、threading），不依赖任何其他文件
- `kiro_bridge.py` 导入 `acp_client.py` 中的 `ACPClient`、`PromptResult`、`PermissionRequest`，是唯一存在硬依赖的文件
- `usage_tracker.py` 完全独立，不 import 任何项目内文件；由调用方（如 OpenClaw 主 Agent）在获取 `KiroBridge.prompt()` 返回的用量数据后，手动调用 `record_task()` 记录
- `test_acp.py` 导入 `acp_client.py`，用于端到端验证 ACP 握手和会话功能
- `SKILL.md` 是纯文本配置，供 OpenClaw 主 Agent 读取以决定任务路由策略，不参与 Python 运行时

### Step 4: 部署 ACP 客户端 (acp_client.py)

纯 Python 标准库实现，零 pip 依赖，约 300 行。

> 📄 源文件：[acp_client.py](./acp_client.py)

核心类与数据结构：
- `ACPClient` — JSON-RPC 2.0 over stdio 客户端，管理 kiro-cli 子进程生命周期
- `ToolCallInfo` — 单次工具调用信息（文件写入、终端命令等）
- `PromptResult` — session/prompt 的完整返回结果
- `PermissionRequest` — Kiro 请求敏感操作授权时的回调参数

```bash
cp acp_client.py "$SKILL_DIR/acp_client.py"
echo "✔ acp_client.py 已部署"
```

### Step 5: 部署生产级桥接器 (kiro_bridge.py)

封装会话管理、懒启动、上下文自动管理。

> 📄 源文件：[kiro_bridge.py](./kiro_bridge.py)

核心功能：
- `KiroBridge` — 生产级封装，支持懒启动、会话复用、上下文 80% 自动切换新会话
- `prompt()` — 发送编码任务，返回结构化结果（含用量数据）
- 支持 `with` 上下文管理器，自动清理子进程

```bash
cp kiro_bridge.py "$SKILL_DIR/kiro_bridge.py"
echo "✔ kiro_bridge.py 已部署"
```

### Step 6: 部署用量追踪器 (usage_tracker.py)

双轨追踪 Kiro Credits 和 Claude API Token 消耗。

> 📄 源文件：[usage_tracker.py](./usage_tracker.py)

核心功能：
- `record_task()` — 记录每次任务的 Kiro Credits 和 Claude API Token 消耗
- 自动计算 Claude API 美元成本（基于 claude-sonnet-4 定价）
- 数据持久化到 `usage_stats.json`

```bash
cp usage_tracker.py "$SKILL_DIR/usage_tracker.py"
echo "✔ usage_tracker.py 已部署"
```

### Step 7: 部署任务路由规则 (SKILL.md)

这是 OpenClaw 的核心路由规则，决定哪些任务发送给 Kiro。

> 📄 源文件：[SKILL.md](./SKILL.md)

定义了：
- 触发关键词（"kiro"、"写代码"、"编程"、"开发"等）
- 发送给 Kiro CLI 的任务类型（编码、文件操作、重构等）
- 由 OpenClaw 主 Agent 直接处理的任务类型（对话、消息、非编码任务等）

```bash
cp SKILL.md "$SKILL_DIR/SKILL.md"
echo "✔ SKILL.md 已部署"
```

---

## Part 3: ACP 协议方法参考

### 核心 ACP 方法

| 方法 | 方向 | 说明 |
|------|------|------|
| `initialize` | Client → Kiro | 握手，声明双方能力 |
| `session/new` | Client → Kiro | 创建新的编码会话 |
| `session/load` | Client → Kiro | 恢复已有会话（保留上下文） |
| `session/prompt` | Client → Kiro | 发送任务，阻塞直到完成 |
| `session/cancel` | Client → Kiro | 取消当前操作 |
| `session/set_mode` | Client → Kiro | 切换 Agent 模式 |
| `session/set_model` | Client → Kiro | 更改会话使用的模型 |
| `session/request_permission` | Kiro → Client | 请求敏感操作授权 |
| `session/update` (notify) | Kiro → Client | 流式推送代码块和工具调用状态 |
| `_kiro.dev/metadata` (notify) | Kiro → Client | 实时推送 Credits + 上下文用量 |

### Kiro 扩展方法（`_kiro.dev/` 前缀）

| 方法 | 类型 | 说明 |
|------|------|------|
| `_kiro.dev/commands/execute` | Request | 执行斜杠命令（如 `/agent swap`） |
| `_kiro.dev/commands/options` | Request | 获取命令自动补全建议 |
| `_kiro.dev/commands/available` | Notification | 会话创建后推送可用命令列表 |
| `_kiro.dev/mcp/server_initialized` | Notification | MCP 服务器初始化完成 |
| `_kiro.dev/compaction/status` | Notification | 上下文压缩进度 |

> `_kiro.dev/*` 扩展是 Kiro 特有的实验性功能，不在公开 ACP 规范中。在 kiro-cli 1.20–1.24 版本中保持稳定。生产环境建议锁定 kiro-cli 版本。

### 会话存储路径

ACP 会话持久化到磁盘：

```
~/.kiro/sessions/cli/
├── <session-id>.json    # 会话元数据和状态
└── <session-id>.jsonl   # 事件日志（对话历史）
```

---

## Part 4: 端到端测试

### Step 8: 快速功能验证

创建一个测试脚本验证完整的 ACP 流程：

> 📄 源文件：[test_acp.py](./test_acp.py)

测试流程：初始化 ACP 连接 → 创建新会话 → 发送测试 prompt → 验证响应。

```bash
cp test_acp.py "$SKILL_DIR/test_acp.py"
echo "✔ test_acp.py 已部署"
```

执行测试：

```bash
python3 "$SKILL_DIR/test_acp.py"
```

期望输出包含 `All tests passed`。如果失败，检查：
- Kiro CLI 是否已登录：`kiro-cli auth status`
- Kiro CLI 路径是否正确：`which kiro-cli`
- 网络是否可访问 Kiro 服务

### Step 9: 通过 KiroBridge 测试编码任务

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.openclaw/workspace/skills/kiro-cli'))
from kiro_bridge import KiroBridge

with KiroBridge() as bridge:
    result = bridge.prompt('Create a simple hello.py that prints Hello World')
    print('Success:', result['success'])
    print('Response:', result['text'][:200])
    print('Tool calls:', len(result['tool_calls']))
    for tc in result['tool_calls']:
        print(f'  [{tc[\"status\"]}] {tc[\"kind\"]}: {tc[\"title\"]}')
    print('Usage:', result['usage'])
"
```

---

## Part 5: 配置 OpenClaw 集成

### Step 10: 注册 Kiro CLI 技能到 OpenClaw

确认技能目录已正确放置：

```bash
ls -la ~/.openclaw/workspace/skills/kiro-cli/
```

期望输出包含 `acp_client.py`、`kiro_bridge.py`、`usage_tracker.py`、`SKILL.md`。

### Step 11: 配置环境变量

在 OpenClaw 的环境配置中添加或更新 Kiro 相关变量。脚本会自动检测已有配置并更新，避免重复追加：

```bash
ENV_FILE="$HOME/.openclaw/.env"

# 需要配置的变量（根据实际安装路径调整）
KIRO_CLI_VALUE="$(which kiro-cli 2>/dev/null || echo "$HOME/.local/bin/kiro-cli")"
KIRO_WORKDIR_VALUE="$HOME/kiro-projects"
KIRO_STATS_VALUE="$HOME/.openclaw/workspace/skills/kiro-cli/usage_stats.json"

# 确保 .env 文件存在
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

# 函数：设置或更新 .env 中的变量
set_env_var() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    # 已存在 → 更新值
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    echo "  ✔ $key 已更新"
  else
    # 不存在 → 追加
    echo "${key}=${value}" >> "$ENV_FILE"
    echo "  ✔ $key 已添加"
  fi
}

# 如果还没有 ACP 配置注释头，先追加一行
if ! grep -q "Kiro CLI ACP Configuration" "$ENV_FILE" 2>/dev/null; then
  echo "" >> "$ENV_FILE"
  echo "# Kiro CLI ACP Configuration" >> "$ENV_FILE"
fi

set_env_var "KIRO_CLI_PATH"      "$KIRO_CLI_VALUE"
set_env_var "KIRO_WORKING_DIR"   "$KIRO_WORKDIR_VALUE"
set_env_var "USAGE_STATS_FILE"   "$KIRO_STATS_VALUE"

echo ""
echo "✔ 环境变量配置完成，当前值："
grep -E "^KIRO_|^USAGE_STATS" "$ENV_FILE"
```

> 多次执行此脚本是安全的（幂等），已有变量会被更新为最新值而非重复追加。

### Step 12: 重启 OpenClaw Gateway

```bash
openclaw gateway restart
```

---

## Part 6: 生产最佳实践

以下挑战及应对策略已默认内置到 `acp_client.py` 和 `kiro_bridge.py` 中，开箱即用。

| 挑战 | 风险 | 内置应对策略 | 实现位置 |
|------|------|-------------|----------|
| 敏感操作未授权执行 | Kiro 可能执行 `rm -rf`、`drop table` 等破坏性命令 | 所有工具调用均需通过 `session/request_permission` 回调审批；默认策略为 `allow_once`，可替换为分级策略（高危拒绝/中危单次/低危放行） | `acp_client.py` `_handle_permission_request()` + `kiro_bridge.py` `_start_acp()` |
| 上下文窗口溢出 | 长会话累积 Token 导致 Kiro 响应质量下降或报错 | `prompt()` 每次调用前检查 `contextUsagePercentage`，超过 80% 自动创建新会话 | `kiro_bridge.py` `prompt()` |
| 任务超时阻塞 | 复杂任务或网络异常导致调用方无限等待 | `session_prompt()` 默认 300s 超时，超时后抛出 `TimeoutError`；调用方可按任务复杂度调整（简单 60s / 复杂 600s） | `acp_client.py` `_send_request_with_id()` |
| kiro-cli 子进程泄漏 | 异常退出后 kiro-cli 及其 MCP 子进程残留占用资源 | `stop()` 递归遍历并终止所有子进程树（`pgrep -P` + `SIGTERM`）；支持 `with` 上下文管理器自动清理 | `acp_client.py` `_kill_children()` + `kiro_bridge.py` `__exit__()` |
| 冷启动延迟 | 每次任务都启动新的 kiro-cli 进程，握手耗时 2-5s | 懒启动 + 进程复用：首次调用时启动，后续调用复用同一进程 | `kiro_bridge.py` `_ensure_acp()` |
| 会话状态丢失 | 多轮编码任务间丢失上下文，Kiro 重复读取文件 | 默认会话持久复用；支持 `session_load()` 恢复历史会话 | `kiro_bridge.py` `_get_default_session()` + `acp_client.py` `session_load()` |
| 多项目上下文污染 | 不同项目的文件和依赖混在同一会话中 | 不同项目使用不同 `cwd` 创建独立会话，MCP 配置自动隔离 | `acp_client.py` `session_new(cwd)` |
| 用量不可见 | 无法追踪 Kiro Credits 和 Claude API 的实际消耗 | `_kiro.dev/metadata` 实时推送 Credits 和上下文用量；`usage_tracker.py` 持久化双轨计费数据 | `acp_client.py` `_handle_line()` + `usage_tracker.py` `record_task()` |
| 任务粒度过大 | 单次 prompt 包含过多工作，上下文消耗高且输出不可预测 | 建议拆分为单文件/单模块粒度的任务；SKILL.md 路由规则引导任务分解 | `SKILL.md` 路由规则 + 调用方任务拆分 |
| stderr 日志丢失 | kiro-cli 的错误输出未被捕获，排查困难 | 独立线程持续读取 stderr 并写入 Python logging | `acp_client.py` `_read_stderr()` |

---

---

## 成本对比

### 双轨计费模型

| 计费轨道 | 处理内容 | 典型消耗 |
|----------|----------|----------|
| Claude API（昂贵） | 意图识别 ~200 Token | 每次编码任务 ~600 Token |
| | 任务分发 ~100 Token | ≈ $0.012 |
| | 结果摘要 ~300 Token | |
| Kiro Credits（独立） | 代码生成 | 每次编码任务 ~8 Credits |
| | 文件读写 | （独立定价） |
| | 终端执行 | |
| | 多轮迭代 | |

### 成本计算

```
集成前（纯 Claude API）：
  ~9,000 Token × 平均($3+$15)/2 ÷ 1M ≈ $0.18/任务
  10 任务/天 × 30 天 ≈ $54/月

集成后（Claude 路由 → Kiro 执行）：
  Claude API: ~600–2,000 Token/任务 ≈ $0.006–$0.018/任务
  + Kiro Credits: ~8 Credits/任务（独立计费）
  10 任务/天 × 30 天 ≈ $3–6/月 Claude API + Kiro 订阅
```

> ⚠ 60–80% 的降低仅针对 Claude API Token 成本。Kiro Credits 独立计费。总成本是否降低取决于 Kiro 订阅方案。核心价值：更低的 Claude 账单 + 代码自动执行和自验证。

---

## 监控指标

| 指标 | 健康值 | 告警阈值 | 处理方式 |
|------|--------|----------|----------|
| 上下文使用 % | < 60% | > 80% | 创建新会话 |
| Credits/任务 | 5–15 | > 30 | 拆分任务 |
| 任务超时率 | < 5% | > 20% | 检查 Kiro 服务/网络 |
| Claude Token/任务 | 300–800 | > 2,000 | 精简系统提示词 |

---

## 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| ACP 握手失败 | `kiro-cli auth status` | 确认已登录；重新执行 `kiro-cli login` |
| `session/new` 无响应 | `KIRO_LOG_LEVEL=debug kiro-cli acp` | 查看详细日志定位问题 |
| 任务超时 | 检查网络连接 | 增加 timeout 参数；拆分大任务 |
| 权限请求未处理 | 检查 `on_permission_request` 回调 | 确认已注册权限处理器 |
| 上下文溢出 | 检查 `_kiro.dev/metadata` | 在 80% 时主动创建新会话 |
| 子进程残留 | `ps aux \| grep kiro` | 调用 `bridge.stop()` 或手动 `kill` |
| MCP 服务器未加载 | 检查 `{cwd}/.kiro/settings/mcp.json` | 确认 MCP 配置文件路径正确 |
| `_kiro.dev/metadata` 无数据 | `kiro-cli version` | 确认版本 ≥ 1.20；此扩展为实验性功能 |
| Credits 不足 | Kiro 返回错误 | 检查 Kiro 订阅状态；升级到 Pro |
| JSON-RPC 解析错误 | 检查 stderr 输出 | 确认 stdin/stdout 未被其他进程干扰 |

## ACP 日志路径

| 平台 | 路径 |
|------|------|
| macOS | `$TMPDIR/kiro-log/kiro-chat.log` |
| Linux | `$XDG_RUNTIME_DIR/kiro-log/kiro-chat.log` |

调试模式：

```bash
KIRO_LOG_LEVEL=debug kiro-cli acp
KIRO_CHAT_LOG_FILE=/tmp/kiro-acp-debug.log kiro-cli acp
```

---

## 参考链接

- [Integrate Kiro CLI into Your AI Agent via ACP（原文）](https://dev.to/aws-builders/integrate-kiro-cli-into-your-ai-agent-via-acp-10jn)
- [AWS Builder Center 原文](https://builder.aws.com/content/3AT0KYNSRVE2zHdfNUyGs295LjP/integrate-kiro-cli-into-openclaw-via-acp-cut-claude-api-token-usage-by-60-80percent)
- [Kiro CLI ACP 官方文档](https://kiro.dev/docs/cli/acp/)
- [ACP 协议规范](https://agentclientprotocol.org/)
- [OpenClaw + Kiro CLI Coding Agent Skill](https://github.com/terrificdm/openclaw-kirocli-coding-agent)
- [OpenClaw ACP Runtime Plugin PR #28662](https://github.com/openclaw/openclaw/pull/28662)
- [Kiro CLI 官方网站](https://kiro.dev/)
- [OpenClaw 文档](https://docs.openclaw.ai)
