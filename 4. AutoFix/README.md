# OpenClaw Gateway 自愈机制配置指南 — Kiro CLI 版

> 当 OpenClaw Gateway 反复崩溃时，自动调用 Kiro CLI 分析日志、修复问题、重启服务，并发送通知。
>
> 基于 [auto-fix-setup-guide.md](https://github.com/kingdoooo/openclaw-setup-guides/blob/main/auto-fix-setup-guide.md) 改编，将 Claude Code 替换为 Kiro CLI 作为自动修复引擎。
>
> 参考: [Kiro CLI 安装与配置](../3.%20KiroCLI/kiro_install_config.md) | [Kiro CLI ACP 集成](../3.%20KiroCLI/kiro_acp_integrate.md)
>
> 幂等性原则：所有操作执行前先检查当前状态，已存在的配置只验证不重复写入，重复执行不会产生副作用。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档所有章节（步骤 1 ~ 步骤 6），理解：
- 目标：配置 systemd 自愈机制 — Gateway 反复崩溃时自动调用 Kiro CLI 修复
- 核心组件：`openclaw-gateway.service`（主服务）+ `openclaw-fix.service`（修复服务）+ `openclaw-fix.sh`（修复脚本）
- 前置依赖：OpenClaw Gateway 以 systemd user service 方式运行 + Kiro CLI 已安装并登录
- 触发条件：60 秒内崩溃 5 次 → OnFailure 触发修复
- 最终验收标准：Gateway 服务运行正常、OnFailure 配置就位、修复脚本可执行、Kiro CLI 认证通过

### 第二步：检查当前环境状态

通读完成后，先执行以下诊断命令，收集当前状态：

```bash
# 1. OpenClaw Gateway 是否以 systemd 方式运行
systemctl --user status openclaw-gateway.service 2>/dev/null || echo "GATEWAY_SERVICE_NOT_FOUND"

# 2. OnFailure 配置是否已存在
cat ~/.config/systemd/user/openclaw-gateway.service.d/auto-fix.conf 2>/dev/null || echo "ONFAILURE_CONF_NOT_FOUND"

# 3. 修复服务是否已配置
cat ~/.config/systemd/user/openclaw-fix.service 2>/dev/null || echo "FIX_SERVICE_NOT_FOUND"

# 4. 修复脚本是否已存在且可执行
ls -la ~/scripts/openclaw-fix.sh 2>/dev/null || echo "FIX_SCRIPT_NOT_FOUND"

# 5. Kiro CLI 是否已安装并认证
kiro-cli version 2>/dev/null || echo "KIRO_CLI_NOT_FOUND"
kiro-cli auth status 2>/dev/null || echo "KIRO_AUTH_UNKNOWN"

# 6. loginctl linger 是否已启用
loginctl show-user "$USER" --property=Linger 2>/dev/null || echo "LINGER_UNKNOWN"

# 7. Python3 是否可用（JSON 验证依赖）
python3 --version 2>/dev/null || echo "PYTHON3_NOT_FOUND"

# 8. 通知渠道是否已配置
openclaw notification list 2>/dev/null | head -1 || echo "NOTIFICATION_NOT_CONFIGURED"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应文档 | 前置条件 | 需要用户确认的情况 |
|------|----------|----------|-------------------|
| 阶段 1：环境检查 | 前置条件 | 无 | Kiro CLI 未安装/未登录时暂停；Gateway 未以 systemd 方式运行时暂停 |
| 阶段 2：配置 Gateway 服务 | 步骤 1 | 阶段 1 通过 | `openclaw-gateway.service` 已存在时跳过，仅验证内容 |
| 阶段 3：配置 OnFailure 触发 | 步骤 2 | 阶段 2 完成 | `auto-fix.conf` 已存在时跳过，仅验证 |
| 阶段 4：创建修复服务和脚本 | 步骤 3-4 | 阶段 3 完成 | `openclaw-fix.service` 和 `openclaw-fix.sh` 已存在时跳过，仅验证 |
| 阶段 5：启用服务 | 步骤 6 | 阶段 4 完成 | linger 已启用且服务已 enable 时跳过 |
| 阶段 6：验证 | 测试 | 阶段 5 完成 | 验证失败时展示错误并等待用户决策 |

### 执行原则

1. **先诊断，后执行** — 不要跳过状态检查直接创建 systemd 文件
2. **幂等性优先** — 每个文件写入前先检查是否已存在且内容一致，已存在则跳过
3. **遇到异常立即暂停** — systemd daemon-reload 失败、服务启动失败等情况，停下来向用户说明
4. **每阶段汇报** — 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续
5. **已完成的步骤可跳过** — 如果诊断发现所有组件已就位且运行正常，直接标记 ✅ 跳过
6. **修改 systemd 文件后必须 daemon-reload** — 每次修改 `.service` 或 `.conf` 文件后执行 `systemctl --user daemon-reload`

---

## 为什么用 Kiro CLI 替代 Claude Code？

| 维度 | Claude Code (`claude -p`) | Kiro CLI (`kiro-cli chat`) |
|------|--------------------------|---------------------------|
| 计费 | Claude API Token（按量，昂贵） | Kiro Credits（独立计费，Free 版可用） |
| 工具能力 | 内置 Read/Write/Edit/Bash | 内置 + MCP 扩展（AWS Docs、Exa Search 等） |
| 上下文管理 | 单次会话 | 支持会话持久化与复用 |
| 安装依赖 | 需要 Claude Max 订阅 | Free 版即可使用 CLI |
| 修复质量 | 依赖 Claude API 模型 | 使用 Kiro AI（Claude Opus 4.6 等），可配置模型 |

> 核心价值：自愈机制不再消耗 Claude API Token，改用 Kiro Credits 独立计费，降低运维成本。

## 架构

```
Gateway 正常运行
    │
    └── 崩溃 → systemd 自动重启（RestartSec=5）
                │
                └── 60秒内崩溃5次
                      │
                      ▼
                    systemd OnFailure 触发
                      │
                      ▼
                    openclaw-fix.service
                      │
                      ▼
                    openclaw-fix.sh
                      │
                      ├── 收集错误日志（日志文件 + journalctl）
                      ├── 验证配置 JSON 合法性
                      ├── 调用 Kiro CLI 分析 + 修复（最多2轮）
                      ├── 修复后验证 JSON + 重启 Gateway
                      └── 发送通知（成功/失败）
```

## 前置条件

| 组件 | 要求 |
|---|---|
| OpenClaw Gateway | systemd user service 方式运行 |
| Kiro CLI | 已安装并登录（`kiro-cli auth status` 确认已认证） |
| Kiro CLI 版本 | ≥ 1.20.0（`kiro-cli version`） |
| 通知渠道 | 自动检测已配置的渠道（Telegram/Discord/Feishu 等，通过 `openclaw notification list`） |
| loginctl linger | 已启用（`loginctl enable-linger $USER`） |
| Python 3 | 用于 JSON 验证（`python3 --version`） |

> Kiro CLI 安装与登录请参考 [kiro_install_config.md](../3.%20KiroCLI/kiro_install_config.md)

## 文件结构

```
~/.config/systemd/user/
├── openclaw-gateway.service              # Gateway 主服务
├── openclaw-gateway.service.d/
│   └── auto-fix.conf                     # OnFailure 触发配置
└── openclaw-fix.service                  # 自动修复服务

~/scripts/
├── openclaw-fix.sh                       # 自动修复主脚本（Kiro CLI 版）
└── safe-gateway-restart.sh               # 安全重启脚本（可选）
```

---

## 步骤 1：配置 Gateway 服务

如果已用 `openclaw gateway install` 安装了 systemd 服务，跳过此步。

### 自动获取所需路径和配置值

以下命令可自动检测当前环境的实际值，无需手动填写：

```bash
# Node.js 路径
NODE_PATH="$(which node)"
echo "Node path: $NODE_PATH"

# Node.js 版本号（用于 PATH 中的 nvm 路径）
NODE_VERSION="$(node -v | sed 's/^v//')"
echo "Node version: $NODE_VERSION"

# OpenClaw 入口文件路径
OPENCLAW_ENTRY="$(which openclaw 2>/dev/null | xargs readlink -f 2>/dev/null || echo "$(npm root -g)/openclaw/dist/index.js")"
echo "OpenClaw entry: $OPENCLAW_ENTRY"

# Gateway Token（从现有 .env 或配置中读取）
GATEWAY_TOKEN="$(grep -s 'OPENCLAW_GATEWAY_TOKEN' ~/.openclaw/.env 2>/dev/null | cut -d= -f2 || openclaw config get gateway.token 2>/dev/null || echo '')"
echo "Gateway token: $GATEWAY_TOKEN"

# Gateway 端口
GATEWAY_PORT="$(grep -s 'OPENCLAW_GATEWAY_PORT' ~/.openclaw/.env 2>/dev/null | cut -d= -f2 || echo '18789')"
echo "Gateway port: $GATEWAY_PORT"
```

### 生成 systemd 服务文件

使用上面获取的值自动生成配置：

```bash
NODE_PATH="$(which node)"
NODE_VERSION="$(node -v | sed 's/^v//')"
OPENCLAW_ENTRY="$(which openclaw 2>/dev/null | xargs readlink -f 2>/dev/null || echo "$(npm root -g)/openclaw/dist/index.js")"
GATEWAY_TOKEN="$(grep -s 'OPENCLAW_GATEWAY_TOKEN' ~/.openclaw/.env 2>/dev/null | cut -d= -f2 || openclaw config get gateway.token 2>/dev/null || echo 'REPLACE_ME')"
GATEWAY_PORT="$(grep -s 'OPENCLAW_GATEWAY_PORT' ~/.openclaw/.env 2>/dev/null | cut -d= -f2 || echo '18789')"

mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/openclaw-gateway.service << EOF
[Unit]
Description=OpenClaw Gateway
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=${NODE_PATH} ${OPENCLAW_ENTRY} gateway --port ${GATEWAY_PORT}
Restart=always
RestartSec=5
KillMode=process
Environment=HOME=%h
Environment=PATH=%h/.local/bin:%h/.nvm/versions/node/v${NODE_VERSION}/bin:/usr/local/bin:/usr/bin:/bin
Environment=OPENCLAW_GATEWAY_PORT=${GATEWAY_PORT}
Environment=OPENCLAW_GATEWAY_TOKEN=${GATEWAY_TOKEN}

[Install]
WantedBy=default.target
EOF

echo "✔ 服务文件已生成: ~/.config/systemd/user/openclaw-gateway.service"
cat ~/.config/systemd/user/openclaw-gateway.service
```

> 如果 `GATEWAY_TOKEN` 输出为 `REPLACE_ME`，说明未能自动检测到 Token，可通过 `cat ~/.openclaw/.env | grep TOKEN` 或 `openclaw config get gateway.token` 手动确认。

## 步骤 2：创建 OnFailure 触发

`~/.config/systemd/user/openclaw-gateway.service.d/auto-fix.conf`：

```ini
[Unit]
# 进入 failed 状态后触发修复服务
OnFailure=openclaw-fix.service
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Restart=always
```

**含义：** 60 秒内崩溃 5 次 → 进入 failed 状态 → 触发 `openclaw-fix.service`。

## 步骤 3：创建修复服务

`~/.config/systemd/user/openclaw-fix.service`：

```ini
[Unit]
Description=OpenClaw Gateway Auto-Fix via Kiro CLI (triggered on failure)

[Service]
Type=oneshot
ExecStart=%h/scripts/openclaw-fix.sh
Environment=HOME=%h
Environment="PATH=%h/.local/bin:%h/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:/usr/bin:/bin"
TimeoutStartSec=750
```

## 步骤 4：创建修复脚本（Kiro CLI 版）

`~/scripts/openclaw-fix.sh`：

```bash
#!/usr/bin/env bash
# openclaw-fix.sh — Called by systemd OnFailure when Gateway repeatedly fails.
# Uses Kiro CLI (instead of Claude Code) for auto-diagnosis and repair.
set -euo pipefail

SERVICE_NAME="${OPENCLAW_GATEWAY_UNIT:-openclaw-gateway.service}"
GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"

# Paths
OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$HOME/.openclaw/openclaw.json}"
LOG_DIR="${OPENCLAW_LOG_DIR:-/tmp/openclaw}"
LOG_DATE="$(date -u +%Y-%m-%d)"
LOG_FILE="${LOG_DIR}/openclaw-${LOG_DATE}.log"

MAX_RETRIES="${OPENCLAW_FIX_MAX_RETRIES:-2}"
KIRO_TIMEOUT_SECS="${OPENCLAW_FIX_KIRO_TIMEOUT_SECS:-300}"

# Single-instance lock (prevent parallel runs)
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/openclaw-fix.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "Another openclaw-fix is already running, exiting."; exit 0; }

detect_notify_channel() {
  # Auto-detect the first configured notification channel from OpenClaw
  local channel_info
  channel_info="$(openclaw notification list 2>/dev/null | head -1 || true)"
  if [[ -z "$channel_info" ]]; then
    NOTIFY_CHANNEL=""
    NOTIFY_TARGET=""
    return
  fi
  # Parse channel type and target from the first configured entry
  # Expected format varies; try common patterns
  NOTIFY_CHANNEL="$(echo "$channel_info" | awk '{print $1}' || true)"
  NOTIFY_TARGET="$(echo "$channel_info" | awk '{print $2}' || true)"
}

notify() {
  local msg="$1"
  [[ -z "$NOTIFY_CHANNEL" || -z "$NOTIFY_TARGET" ]] && return 0
  openclaw message send --channel "$NOTIFY_CHANNEL" --target "$NOTIFY_TARGET" --message "$msg" 2>/dev/null || true
}

find_kiro_cli() {
  local k
  k="$(command -v kiro-cli 2>/dev/null || true)"
  if [[ -n "$k" && -x "$k" ]]; then echo "$k"; return 0; fi
  for candidate in "$HOME/.local/bin/kiro-cli" /usr/local/bin/kiro-cli; do
    if [[ -x "$candidate" ]]; then echo "$candidate"; return 0; fi
  done
  echo ""
}

collect_errors() {
  echo "=== tail(log) errors ==="
  if [[ -f "$LOG_FILE" ]]; then
    tail -80 "$LOG_FILE" 2>/dev/null | grep -i "error\|fatal\|invalid\|failed\|EADDRINUSE" | tail -20 || true
  fi
  echo ""
  echo "=== journalctl ($SERVICE_NAME) ==="
  journalctl --user -u "$SERVICE_NAME" --no-pager -n 40 2>/dev/null || true
}

validate_config_json() {
  if [[ -f "$OPENCLAW_CONFIG_PATH" ]]; then
    python3 -m json.tool "$OPENCLAW_CONFIG_PATH" >/dev/null 2>&1
  fi
}

restart_and_check() {
  systemctl --user reset-failed "$SERVICE_NAME" 2>/dev/null || true
  systemctl --user restart "$SERVICE_NAME" 2>/dev/null || true
  sleep 8
  systemctl --user is-active "$SERVICE_NAME" >/dev/null 2>&1
}

# ---- Main ----
detect_notify_channel
ERROR_CONTEXT="$(collect_errors)"

# Check if config JSON is valid
if [[ -f "$OPENCLAW_CONFIG_PATH" ]] && ! validate_config_json; then
  notify "🔴 Gateway config JSON invalid: $OPENCLAW_CONFIG_PATH"
  exit 1
fi

# Find Kiro CLI
KIRO_CLI="$(find_kiro_cli)"
if [[ -z "$KIRO_CLI" ]]; then
  notify "🔴 $SERVICE_NAME failed. Kiro CLI not found; cannot auto-fix."
  exit 1
fi

# Verify Kiro CLI auth
if ! "$KIRO_CLI" auth status 2>&1 | grep -qi "authenticated\|logged in\|active"; then
  notify "🔴 $SERVICE_NAME failed. Kiro CLI not authenticated; run 'kiro-cli login' first."
  exit 1
fi

notify "🔧 $SERVICE_NAME failed. Attempting auto-fix via Kiro CLI…"

for attempt in $(seq 1 "$MAX_RETRIES"); do
  FIX_PROMPT="OpenClaw Gateway repeatedly failed. Fix the issue and verify.

Service: $SERVICE_NAME
Gateway port: $GATEWAY_PORT
Config file: $OPENCLAW_CONFIG_PATH

Error context:
$ERROR_CONTEXT

Rules:
- Prefer minimal changes.
- Do NOT remove known-good baseline plugins unless clearly broken.
- After changes, verify JSON: python3 -m json.tool $OPENCLAW_CONFIG_PATH > /dev/null
- Then restart: systemctl --user restart $SERVICE_NAME

Show what you changed."

  fix_output=$(timeout "$KIRO_TIMEOUT_SECS" "$KIRO_CLI" chat \
    --no-interactive \
    --trust-all-tools \
    --model claude-opus-4-6 \
    -p "$FIX_PROMPT" \
    2>&1 || echo "Kiro CLI failed or timed out")

  echo "[openclaw-fix] Attempt $attempt output (tail):"
  echo "$fix_output" | tail -40

  # Verify config JSON is still valid after fix
  if [[ -f "$OPENCLAW_CONFIG_PATH" ]] && ! validate_config_json; then
    notify "🔴 Auto-fix attempt $attempt produced invalid JSON. Not restarting."
    continue
  fi

  if restart_and_check; then
    notify "✅ Gateway auto-fixed and restarted successfully (attempt $attempt)."
    exit 0
  fi

  ERROR_CONTEXT="$(collect_errors)"
done

notify "🔴 Gateway auto-fix failed after $MAX_RETRIES attempts. Manual intervention needed."
exit 1
```

```bash
chmod +x ~/scripts/openclaw-fix.sh
```

### 与 Claude Code 版本的关键差异

| 部分 | Claude Code 版 | Kiro CLI 版 |
|------|---------------|-------------|
| 查找命令 | `find_claude()` → `claude` | `find_kiro_cli()` → `kiro-cli` |
| 认证检查 | 无 | 新增 `kiro-cli auth status` 检查 |
| 调用方式 | `claude -p "$PROMPT" --allowedTools "Read,Write,Edit,Bash" --max-turns 10` | `kiro-cli chat --no-interactive --trust-all-tools --model claude-opus-4-6 -p "$PROMPT"` |
| 超时变量 | `OPENCLAW_FIX_CLAUDE_TIMEOUT_SECS` | `OPENCLAW_FIX_KIRO_TIMEOUT_SECS` |
| 计费 | Claude API Token | Kiro Credits（独立） |

## 步骤 5：（可选）安全重启脚本

`~/scripts/safe-gateway-restart.sh` — 手动重启时也带自动修复能力：

```bash
#!/usr/bin/env bash
# safe-gateway-restart.sh — Restart with optional auto-fix on failure via Kiro CLI.
set -euo pipefail

REASON="${1:-manual restart}"
MAX_RETRIES="${SAFE_RESTART_MAX_RETRIES:-2}"
SERVICE_NAME="${OPENCLAW_GATEWAY_UNIT:-openclaw-gateway.service}"
LOG_FILE="${OPENCLAW_LOG_FILE:-/tmp/openclaw/openclaw-$(date -u +%Y-%m-%d).log}"

find_kiro_cli() {
  local k
  k="$(command -v kiro-cli 2>/dev/null || true)"
  if [[ -n "$k" && -x "$k" ]]; then echo "$k"; return 0; fi
  for candidate in "$HOME/.local/bin/kiro-cli" /usr/local/bin/kiro-cli; do
    if [[ -x "$candidate" ]]; then echo "$candidate"; return 0; fi
  done
  echo ""
}

check_errors() {
  local errors=""
  if [[ -f "$LOG_FILE" ]]; then
    errors=$(tail -60 "$LOG_FILE" | grep -i "invalid config\|Config validation failed\|plugin.*not found\|ERROR.*plugin" | tail -10 || true)
  fi
  local status_output
  status_output=$(openclaw gateway status 2>&1 || true)
  if echo "$status_output" | grep -qi "invalid config\|Config invalid"; then
    errors="$errors
$status_output"
  fi
  echo "$errors"
}

do_restart() {
  echo "[$(date -u +%H:%M:%S)] Restarting gateway (reason: $REASON)…"
  systemctl --user restart "$SERVICE_NAME" 2>&1 || openclaw gateway restart 2>&1 || true
  echo "[$(date -u +%H:%M:%S)] Waiting 6s for gateway to stabilize…"
  sleep 6
}

KIRO_CLI="$(find_kiro_cli)"
KIRO_TIMEOUT="${SAFE_RESTART_KIRO_TIMEOUT_SECS:-300}"

for attempt in $(seq 1 $((MAX_RETRIES + 1))); do
  do_restart
  errors="$(check_errors)"

  if [[ -z "$errors" || "$errors" =~ ^[[:space:]]*$ ]]; then
    echo "✅ Gateway restarted successfully (attempt $attempt)"
    exit 0
  fi

  echo "❌ Errors detected: $errors"

  if [[ $attempt -gt $MAX_RETRIES ]] || [[ -z "$KIRO_CLI" ]]; then
    echo "🔴 Failed after $MAX_RETRIES attempts."
    exit 1
  fi

  FIX_PROMPT="OpenClaw gateway restart failed:
$errors

Fix the issue. Prefer minimal changes.
After fixing, verify JSON: python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null"

  timeout "$KIRO_TIMEOUT" "$KIRO_CLI" chat \
    --no-interactive \
    --trust-all-tools \
    --model claude-opus-4-6 \
    -p "$FIX_PROMPT" \
    2>&1 | tail -40
done
```

## 步骤 6：启用

```bash
# 创建 drop-in 目录
mkdir -p ~/.config/systemd/user/openclaw-gateway.service.d/

# 重新加载 systemd
systemctl --user daemon-reload

# 启用 linger（SSH 断开后服务继续运行）
loginctl enable-linger $USER

# 启动 Gateway
systemctl --user enable --now openclaw-gateway.service
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENCLAW_GATEWAY_UNIT` | `openclaw-gateway.service` | systemd 服务名 |
| `OPENCLAW_GATEWAY_PORT` | `18789` | Gateway 端口 |
| `OPENCLAW_CONFIG_PATH` | `~/.openclaw/openclaw.json` | 配置文件路径 |
| `OPENCLAW_LOG_DIR` | `/tmp/openclaw` | 日志目录 |
| `OPENCLAW_FIX_MAX_RETRIES` | `2` | Kiro CLI 最大修复轮次 |
| `OPENCLAW_FIX_KIRO_TIMEOUT_SECS` | `300` | Kiro CLI 单次超时 |

## 工作原理

1. **systemd Restart=always** — 普通崩溃直接重启，5 秒间隔
2. **StartLimitBurst=5 / StartLimitIntervalSec=60** — 60 秒内崩 5 次进入 failed
3. **OnFailure=openclaw-fix.service** — failed 后触发修复
4. **openclaw-fix.sh** — 收集日志 → Kiro CLI 分析 → 最小修复 → 验证 JSON → 重启 → 通知
5. **flock 单实例锁** — 防止多个修复进程同时跑

## 关键设计

- **Kiro CLI `--no-interactive --trust-all-tools`**：非交互模式 + 信任所有工具，适合无人值守的自动修复场景
- **认证前置检查**：修复前验证 `kiro-cli auth status`，避免因未登录导致修复失败
- **Kiro Credits 独立计费**：自愈修复不消耗 Claude API Token，运维成本可控
- **MCP 扩展能力**：如果配置了 AWS Documentation MCP，Kiro CLI 修复时可自动查阅 AWS 文档获取正确配置
- **最小变更原则**：提示词明确要求 "prefer minimal changes"，避免大改
- **JSON 验证**：修复后先验证 JSON 合法性，不合法不重启
- **超时保护**：Kiro CLI 单次 300 秒超时，总服务 750 秒超时
- **通知**：自动检测 OpenClaw 已配置的通知渠道（`openclaw notification list`），取第一个渠道发送，无需手动配置

## 进阶：通过 ACP 实现更精细的修复控制

如果需要更精细的修复流程控制（如会话复用、用量追踪、权限审批），可以将修复脚本从直接调用 `kiro-cli chat` 升级为通过 ACP 协议调用。

### ACP 版修复脚本片段

```bash
# 替换 kiro-cli chat 直接调用，改用 ACP 客户端
SKILL_DIR="$HOME/.openclaw/workspace/skills/kiro-cli"

fix_output=$(timeout "$KIRO_TIMEOUT_SECS" python3 -c "
import sys; sys.path.insert(0, '$SKILL_DIR/scripts')
from kiro_bridge import KiroBridge

with KiroBridge() as bridge:
    result = bridge.prompt('''$FIX_PROMPT''', project='gateway-fix', timeout=$KIRO_TIMEOUT_SECS)
    print(result['text'])
    if result.get('usage'):
        print(f\"Credits used: {result['usage'].get('kiro_credits', 'N/A')}\")
" 2>&1 || echo "Kiro ACP fix failed or timed out")
```

### ACP 版优势

| 特性 | 直接调用 `kiro-cli chat` | ACP 客户端 |
|------|------------------------|-----------|
| 会话复用 | 每次新会话 | 可复用上次修复会话的上下文 |
| 用量追踪 | 无 | 自动记录 Credits 消耗 |
| 权限控制 | `--trust-all-tools` 全放行 | 可按操作类型分级审批 |
| 上下文管理 | 无 | 自动在 80% 时轮换会话 |
| 多项目隔离 | 无 | 不同修复任务独立上下文 |

> ACP 集成详情参见 [kiro_acp_integrate.md](../3.%20KiroCLI/kiro_acp_integrate.md)

## 测试

```bash
# 手动触发修复（模拟）
bash ~/scripts/openclaw-fix.sh

# 安全重启
bash ~/scripts/safe-gateway-restart.sh "测试重启"

# 验证 Kiro CLI 可用性
kiro-cli auth status
kiro-cli version
```

## 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| `kiro-cli` 命令不存在 | `ls ~/.local/bin/kiro-cli` | 参考 [kiro_install_config.md](../3.%20KiroCLI/kiro_install_config.md) 安装 |
| Kiro CLI 未认证 | `kiro-cli auth status` | 执行 `kiro-cli login --license free --use-device-flow` |
| 修复超时 | 检查网络连接 | 增加 `OPENCLAW_FIX_KIRO_TIMEOUT_SECS`；拆分修复任务 |
| 修复后 JSON 无效 | `python3 -m json.tool ~/.openclaw/openclaw.json` | 手动检查并修复 JSON 语法 |
| systemd 服务未触发 | `systemctl --user status openclaw-fix.service` | 确认 `auto-fix.conf` 已正确放置并执行 `daemon-reload` |
| 通知未发送 | `openclaw notification list` | 确认至少配置了一个通知渠道（Telegram/Discord/Feishu 等） |
| Kiro Credits 不足 | Kiro CLI 返回错误 | 检查 Kiro 订阅状态；升级到 Pro |
| 修复质量不佳 | 检查 Kiro CLI 模型配置 | 在 `~/.kiro/settings/settings.json` 中设置 `defaultModel` 为 `claude-opus-4-6` |

## 参考

- [auto-fix-setup-guide.md（原版 Claude Code 方案）](https://github.com/kingdoooo/openclaw-setup-guides/blob/main/auto-fix-setup-guide.md)
- [Kiro CLI 安装与配置](../3.%20KiroCLI/kiro_install_config.md)
- [Kiro CLI ACP 集成](../3.%20KiroCLI/kiro_acp_integrate.md)
- [Kiro 官方网站](https://kiro.dev/)
- [OpenClaw 文档](https://docs.openclaw.ai)
- [systemd OnFailure](https://www.freedesktop.org/software/systemd/man/systemd.unit.html#OnFailure=)
