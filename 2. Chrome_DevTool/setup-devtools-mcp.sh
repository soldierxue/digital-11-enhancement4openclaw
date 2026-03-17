#!/bin/bash
# setup-devtools-mcp.sh — 根据环境检测结果自动配置 Chrome DevTools MCP
# 供 OpenClaw Agent 调用，自动完成：
#   1. 运行环境检测
#   2. 按环境类型配置 Chrome DevTools MCP 服务器
#   3. 配置 OpenClaw browser 参数
#
# 用法:
#   bash setup-devtools-mcp.sh              # 自动检测并配置
#   bash setup-devtools-mcp.sh --headless   # 强制 headless 模式
#   bash setup-devtools-mcp.sh --headed     # 强制 headed 模式

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${HOME}/.openclaw/openclaw.json"
FORCE_MODE="${1:-auto}"

echo "╔══════════════════════════════════════════════════════╗"
echo "║  Chrome DevTools MCP — 自动环境检测与配置            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# --- Step 1: 环境检测 ---

echo "▶ Step 1: 检测运行环境..."
echo ""

if [ ! -f "${SCRIPT_DIR}/detect-display-env.sh" ]; then
  echo "✘ 找不到 detect-display-env.sh，请确认脚本在同一目录下"
  exit 1
fi

ENV_JSON=$(bash "${SCRIPT_DIR}/detect-display-env.sh")

# 解析 JSON（使用 python3，Ubuntu 自带）
eval "$(echo "$ENV_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'HAS_DISPLAY={str(d[\"has_display\"]).lower()}')
print(f'DISPLAY_TYPE={d[\"display_type\"]}')
print(f'CHROME_INSTALLED={str(d[\"chrome_installed\"]).lower()}')
print(f'CHROME_VERSION={d[\"chrome_version\"]}')
print(f'NODE_INSTALLED={str(d[\"node_installed\"]).lower()}')
print(f'NODE_VERSION={d[\"node_version\"]}')
print(f'RECOMMENDED_MODE={d[\"recommended_mode\"]}')
")"

echo "  显示环境: ${DISPLAY_TYPE}"
echo "  Chrome:   ${CHROME_INSTALLED} ${CHROME_VERSION:+(${CHROME_VERSION})}"
echo "  Node.js:  ${NODE_INSTALLED} ${NODE_VERSION:+(${NODE_VERSION})}"
echo "  推荐模式: ${RECOMMENDED_MODE}"
echo ""

# --- 确定最终模式 ---

if [ "$FORCE_MODE" = "--headless" ]; then
  MODE="headless"
  echo "  ⚙ 强制使用 headless 模式"
elif [ "$FORCE_MODE" = "--headed" ]; then
  MODE="headed"
  echo "  ⚙ 强制使用 headed 模式"
else
  MODE="$RECOMMENDED_MODE"
  echo "  ⚙ 自动选择: ${MODE} 模式"
fi
echo ""

# --- Step 2: 前置检查 ---

echo "▶ Step 2: 前置条件检查..."
echo ""

ERRORS=0

if [ "$NODE_INSTALLED" != "true" ]; then
  echo "  ✘ Node.js 未安装（需要 >= v20.19）"
  echo "    安装方法: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash"
  echo "              source ~/.bashrc && nvm install --lts"
  ERRORS=$((ERRORS + 1))
else
  NODE_MAJOR=$(echo "$NODE_VERSION" | sed 's/v//' | cut -d. -f1)
  if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "  ✘ Node.js 版本过低 (${NODE_VERSION})，需要 >= v20.19"
    ERRORS=$((ERRORS + 1))
  else
    echo "  ✔ Node.js ${NODE_VERSION}"
  fi
fi

if [ "$CHROME_INSTALLED" != "true" ]; then
  echo "  ⚠ Chrome 未安装（MCP 可自动下载 Chromium，但建议先安装 Chrome）"
  echo "    参考本目录 README.md 的 Chrome 安装步骤"
else
  echo "  ✔ Chrome ${CHROME_VERSION}"
fi

if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo "✘ 有 ${ERRORS} 个前置条件未满足，请先修复后重试"
  exit 1
fi

echo ""

# --- Step 3: 配置 OpenClaw ---

echo "▶ Step 3: 写入 OpenClaw 配置..."
echo ""

mkdir -p "$(dirname "$CONFIG_PATH")"

# 备份
if [ -f "$CONFIG_PATH" ]; then
  cp "$CONFIG_PATH" "${CONFIG_PATH}.bak.$(date +%Y%m%d%H%M%S)"
  echo "  ✔ 已备份现有配置"
fi

if [ "$MODE" = "headless" ]; then
  # ===== 无显示器服务器环境 =====
  echo "  📋 配置方案: 无显示器服务器（headless）"
  echo ""
  echo "  browser.headless  = true"
  echo "  browser.noSandbox = true"
  echo "  MCP args: --headless"
  echo ""

  python3 -c "
import json, os

config_path = os.path.expanduser('${CONFIG_PATH}')
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

# browser 配置 — headless 服务器
if 'browser' not in config:
    config['browser'] = {}
config['browser']['enabled'] = True
config['browser']['headless'] = True
config['browser']['noSandbox'] = True
config['browser']['evaluateEnabled'] = True

# MCP 配置 — headless 模式
if 'mcpServers' not in config:
    config['mcpServers'] = {}
config['mcpServers']['chrome-devtools'] = {
    'command': 'npx',
    'args': ['-y', 'chrome-devtools-mcp@latest', '--headless']
}

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print('  ✔ 配置已写入 (headless 模式)')
"

else
  # ===== 有显示器环境（DCV / X11 / Wayland / VNC）=====
  echo "  📋 配置方案: 图形桌面环境（headed）— ${DISPLAY_TYPE}"
  echo ""
  echo "  browser.headless  = false"
  echo "  browser.noSandbox = false"
  echo "  MCP args: (无 --headless)"
  echo ""

  python3 -c "
import json, os

config_path = os.path.expanduser('${CONFIG_PATH}')
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

# browser 配置 — headed 桌面
if 'browser' not in config:
    config['browser'] = {}
config['browser']['enabled'] = True
config['browser']['headless'] = False
config['browser']['noSandbox'] = False
config['browser']['evaluateEnabled'] = True
config['browser']['defaultProfile'] = 'openclaw'

# 双 Profile 配置
config['browser']['profiles'] = {
    'chrome': {
        'cdpUrl': 'http://127.0.0.1:9222',
        'driver': 'extension',
        'attachOnly': True,
        'color': '#00AA00'
    },
    'openclaw': {
        'color': '#FF4500'
    }
}

# MCP 配置 — headed 模式（不加 --headless）
if 'mcpServers' not in config:
    config['mcpServers'] = {}
config['mcpServers']['chrome-devtools'] = {
    'command': 'npx',
    'args': ['-y', 'chrome-devtools-mcp@latest']
}

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print('  ✔ 配置已写入 (headed 模式，含双 Profile)')
"

fi

echo ""

# --- Step 4: 预下载 MCP ---

echo "▶ Step 4: 预下载 chrome-devtools-mcp..."
echo ""

if npx -y chrome-devtools-mcp@latest --help >/dev/null 2>&1; then
  echo "  ✔ chrome-devtools-mcp 已就绪"
else
  echo "  ⚠ 预下载未完成（首次使用时会自动下载）"
fi

echo ""

# --- Step 5: 重启 Gateway ---

echo "▶ Step 5: 重启 OpenClaw Gateway..."
echo ""

if command -v openclaw &>/dev/null; then
  if openclaw gateway restart 2>/dev/null; then
    echo "  ✔ Gateway 已重启"
  else
    echo "  ⚠ Gateway 重启失败，请手动执行: openclaw gateway restart"
  fi
else
  echo "  ⚠ openclaw 命令不可用，请手动重启 Gateway"
fi

echo ""

# --- 完成 ---

echo "╔══════════════════════════════════════════════════════╗"
echo "║  配置完成                                            ║"
echo "╠══════════════════════════════════════════════════════╣"

if [ "$MODE" = "headless" ]; then
  echo "║  模式: headless（无显示器服务器）                    ║"
  echo "║  Chrome 将在后台无头运行                             ║"
  echo "║                                                      ║"
  echo "║  测试: 在 OpenClaw 对话中输入                        ║"
  echo "║    「打开 https://www.google.com 并截图」            ║"
else
  echo "║  模式: headed（${DISPLAY_TYPE} 图形桌面）            ║"
  echo "║  Chrome 将在桌面上可见运行                           ║"
  echo "║                                                      ║"
  echo "║  可选: 在 Chrome 地址栏输入                          ║"
  echo "║    chrome://inspect/#remote-debugging                ║"
  echo "║  勾选启用 Remote Debugging 以支持双 Profile          ║"
  echo "║                                                      ║"
  echo "║  测试: 在 OpenClaw 对话中输入                        ║"
  echo "║    「打开 https://www.google.com 并截图」            ║"
fi

echo "╚══════════════════════════════════════════════════════╝"
